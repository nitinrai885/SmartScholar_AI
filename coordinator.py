"""
coordinator.py - runs the FAN-OUT / FAN-IN workflow.

    Intake  ->  Eligibility  ->  +-- Merit Agent --+
                                 |                 +-->  Panel Manager  ->  decision
                                 +-- Need Agent  --+
                         (fan-out: run together)      (fan-in: collect and combine)

The fan-out is asyncio.gather(): Merit and Need are started together and the Panel Manager
only starts after BOTH have finished and written their results to shared memory.
"""
import asyncio
from datetime import datetime

import config
from agents.eligibility_agent import EligibilityAgent
from agents.intake_agent import IntakeAgent
from agents.merit_agent import MeritAgent
from agents.need_agent import NeedAgent
from agents.panel_manager import PanelManager
from kernel_setup import build_kernel, check_groq_model
from memory.execution_log import ExecutionLog, now_iso, trace_entry
from memory.shared_memory import SharedMemory
from rag.rag_engine import RagEngine


class Coordinator:
    def __init__(self, use_llm=True, memory_path=None, log_path=None, rubric_path=None):
        self.memory = SharedMemory(memory_path or config.MEMORY_PATH)
        self.log = ExecutionLog(log_path or config.LOG_PATH)
        self.rag = RagEngine(rubric_path or config.RUBRIC_PATH)

        self.model_id, self.llm_message = None, "LLM disabled by the caller"
        if use_llm:
            ok, model_id, self.llm_message = check_groq_model()
            self.model_id = model_id if ok else None
        self.llm_on = self.model_id is not None
        self.mode = (f"LLM mode (Groq model: {self.model_id})" if self.llm_on
                     else "Demo mode (deterministic, no LLM)")

    # A fresh kernel is built for every evaluation (cheap, and avoids async-client reuse problems).
    def create_kernel(self):
        return build_kernel(self.model_id)

    def create_agents(self, kernel):
        return {
            "intake": IntakeAgent(kernel, self.memory, self.log, self.llm_on),
            "eligibility": EligibilityAgent(kernel, self.rag, self.memory, self.log),
            "merit": MeritAgent(kernel, self.rag, self.memory, self.log),
            "need": NeedAgent(kernel, self.rag, self.memory, self.log),
            "panel": PanelManager(kernel, self.rag, self.memory, self.log, self.llm_on),
        }

    async def _safe(self, application_id, agent_name, coroutine):
        """Run one agent; if it crashes, record a clear error instead of stopping everything."""
        started = now_iso()
        try:
            return await coroutine
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            self.log.log(application_id, agent_name, "Agent failed", "-", message, "error")
            return trace_entry(agent_name, "Agent failed", [], "-", message, "error", started)

    async def evaluate_async(self, raw_input):
        """Evaluate one application and return its final shared-memory record."""
        application_id = str(raw_input.get("application_id") or "").strip()
        if not application_id:      # never invent real data, but memory needs some key
            application_id = "UNASSIGNED-" + datetime.now().strftime("%Y%m%d%H%M%S")
        self.memory.create_application(application_id)
        self.log.log(application_id, "Coordinator", "Application received", "Raw submission", "Workflow started")

        kernel = self.create_kernel()
        agents = self.create_agents(kernel)
        trace = []

        # STEP 2 - Intake
        trace.append(await self._safe(application_id, "Intake Agent", agents["intake"].run(application_id, raw_input)))

        if self.memory.get(application_id)["intake_result"].get("valid"):
            # STEP 3 - Eligibility
            trace.append(await self._safe(application_id, "Eligibility Agent", agents["eligibility"].run(application_id)))
            # STEPS 4 and 5 - FAN-OUT: Merit and Need run at the same time
            self.log.log(application_id, "Coordinator", "Fan-out", "Eligibility done",
                         "Starting Merit Agent and Need Agent together")
            merit_trace, need_trace = await asyncio.gather(
                self._safe(application_id, "Merit Agent", agents["merit"].run(application_id)),
                self._safe(application_id, "Need Agent", agents["need"].run(application_id)))
            trace += [merit_trace, need_trace]
        else:
            for name in ("Eligibility Agent", "Merit Agent", "Need Agent"):
                note = "Skipped: application is incomplete, nothing to evaluate"
                trace.append(trace_entry(name, "Skipped", [], "-", note, "skipped", now_iso()))
                self.log.log(application_id, name, "Skipped", "-", note, "skipped")

        # STEPS 6-8 - FAN-IN: Panel Manager collects everything, scores and decides
        self.log.log(application_id, "Coordinator", "Fan-in", "Merit and Need finished",
                     "Starting Panel Manager")
        trace.append(await self._safe(application_id, "Panel Manager", agents["panel"].run(application_id)))

        if not self.memory.get(application_id)["final_decision"]:   # Panel Manager itself crashed
            error_text = trace[-1]["output_summary"]
            self.memory.update(application_id, "final_decision", {
                "decision": "Error", "status": "System error", "final_score": None,
                "eligibility": "Not evaluated", "rubric_references": [], "tools_used": [],
                "justification": "The evaluation could not be completed: " + error_text})
        self.memory.update(application_id, "execution_trace", trace)
        self.log.log(application_id, "Coordinator", "Workflow finished", "-",
                     "Decision: " + str(self.memory.get(application_id)["final_decision"].get("decision")))
        return self.memory.get(application_id)

    def evaluate(self, raw_input):
        """Normal (blocking) version for scripts, tests and Streamlit."""
        return asyncio.run(self.evaluate_async(raw_input))
