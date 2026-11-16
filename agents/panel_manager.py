"""AGENT 5 - Panel Manager (fan-in): combines all results into the final decision."""
import json

from semantic_kernel.functions import kernel_function

import config
from kernel_setup import ask_llm, call_tool, clean_for_prompt
from memory.execution_log import now_iso, trace_entry
from rag.rag_engine import select_references
from tools import panel_tools

AGENT_NAME = "Panel Manager"
PLUGIN = "PanelTools"


class PanelTools:
    @kernel_function(name="calculate_weighted_score",
                     description="Final score = merit x merit weight + need x need weight.")
    def calculate_weighted_score(self, merit_score: float, need_score: float,
                                 merit_weight: float, need_weight: float) -> str:
        return json.dumps(panel_tools.calculate_weighted_score(merit_score, need_score,
                                                               merit_weight, need_weight))

    @kernel_function(name="generate_final_decision",
                     description="Award, Waitlist or Reject from the final score and eligibility.")
    def generate_final_decision(self, final_score: float, eligible: bool,
                                award_min: float, waitlist_min: float) -> str:
        return json.dumps(panel_tools.generate_final_decision(final_score, eligible, award_min, waitlist_min))


def _merge_references(*lists):
    """Combine reference lists without repeats, keeping order."""
    merged, seen = [], set()
    for references in lists:
        for ref in references:
            if ref["clause_id"] not in seen:
                seen.add(ref["clause_id"])
                merged.append(ref)
    return merged


class PanelManager:
    def __init__(self, kernel, rag, memory, log, llm_on):
        self.kernel, self.rag, self.memory, self.log, self.llm_on = kernel, rag, memory, log, llm_on
        kernel.add_plugin(PanelTools(), plugin_name=PLUGIN)

    async def run(self, application_id):
        started, tools_used = now_iso(), []
        record = self.memory.get(application_id)

        # Fan-in check: do we have everything we need? Never assume missing information.
        missing_results = [name for name in ("eligibility_result", "merit_result", "need_result")
                           if not record.get(name)]
        intake = record.get("intake_result", {})
        if not intake.get("valid") or missing_results:
            return self._incomplete(application_id, record, intake, missing_results, started)

        eligibility, merit, need = record["eligibility_result"], record["merit_result"], record["need_result"]
        weights, limits = config.WEIGHTS, config.THRESHOLDS

        retrieved = self.rag.retrieve("final score weights and decision thresholds",
                                      sections=["Score Weights", "Decision Thresholds"], n_results=2)
        self.log.log(application_id, AGENT_NAME, "RAG retrieval", "Query: weights and thresholds",
                     "Retrieved clauses: " + ", ".join(c["clause_id"] for c in retrieved))

        score = await call_tool(self.kernel, PLUGIN, "calculate_weighted_score", tools_used,
                                merit_score=merit["total_merit_score"], need_score=need["need_score"],
                                merit_weight=weights["merit"], need_weight=weights["need"])
        decision = await call_tool(self.kernel, PLUGIN, "generate_final_decision", tools_used,
                                   final_score=score["final_score"], eligible=eligibility["eligible"],
                                   award_min=limits["award"], waitlist_min=limits["waitlist"])

        references = _merge_references(eligibility["rubric_references"], merit["rubric_references"],
                                       need["rubric_references"],
                                       select_references(retrieved, {config.CLAUSE["weights"], config.CLAUSE["decision"]}))
        ids = ", ".join(r["clause_id"] for r in references)

        justification = self._justification(eligibility, merit, need, score, decision, ids)
        llm_text = None
        if self.llm_on:
            llm_text = await ask_llm(self.kernel, self._llm_prompt(record, eligibility, score, decision))

        final = {
            "decision": decision["decision"],
            "status": "Completed",
            "final_score": score["final_score"],
            "merit_score": merit["total_merit_score"],
            "need_score": need["need_score"],
            "weights": weights,
            "eligibility": "Passed" if eligibility["eligible"] else "Failed",
            "failed_rules": eligibility["failed_rules"],
            "formula": score["formula"],
            "justification": justification,
            "llm_explanation": llm_text,
            "rubric_references": references,
            "tools_used": tools_used,
        }
        self.memory.update(application_id, "final_decision", final)

        input_summary = f"Merit {merit['total_merit_score']}, need {need['need_score']}, eligibility {final['eligibility']}"
        output_summary = f"Final score {score['final_score']} -> {decision['decision']}"
        self.log.log(application_id, AGENT_NAME, "[fan-in] Weighted score and final decision",
                     input_summary, output_summary)
        return trace_entry(AGENT_NAME, "[fan-in] Weighted score and final decision", tools_used,
                           input_summary, output_summary, "success", started)

    # ------------------------------------------------------------------ helpers
    def _justification(self, eligibility, merit, need, score, decision, ids):
        weights, limits = config.WEIGHTS, config.THRESHOLDS
        numbers = (f"Merit score {merit['total_merit_score']}/100 (weight {weights['merit']:.0%}) and financial need "
                   f"score {need['need_score']}/100 (weight {weights['need']:.0%}) give a final weighted score of "
                   f"{score['final_score']} [{config.CLAUSE['weights']}].")
        bands = (f"Thresholds: {limits['award']} or more is Award, {limits['waitlist']} to below {limits['award']} "
                 f"is Waitlist, below {limits['waitlist']} is Reject [{config.CLAUSE['decision']}].")
        if not eligibility["eligible"]:
            text = (f"Decision: Reject. The student failed a mandatory eligibility rule, so the decision is Reject "
                    f"whatever the score. Failed: {'; '.join(eligibility['failed_rules'])}. {numbers} "
                    f"The score is shown for information only. {bands}")
        else:
            text = (f"Decision: {decision['decision']}. The student meets all mandatory eligibility requirements. "
                    f"{numbers} {decision['reason']}. {bands}")
        return text + f" Rubric references: {ids}."

    def _llm_prompt(self, record, eligibility, score, decision):
        return ("You are writing for a scholarship applicant. In 3 short, plain sentences explain the decision below. "
                "Use ONLY the facts given. Do not change any number, do not invent rules, do not add advice.\n"
                f"Student: {clean_for_prompt(record['student_name'])}\n"
                f"Eligibility: {'Passed' if eligibility['eligible'] else 'Failed - ' + clean_for_prompt('; '.join(eligibility['failed_rules']))}\n"
                f"Final weighted score: {score['final_score']} out of 100\n"
                f"Decision: {decision['decision']}")

    def _incomplete(self, application_id, record, intake, missing_results, started):
        problems = intake.get("missing_fields", []) + intake.get("invalid_fields", [])
        if not problems:
            problems = [f"agent result not available: {name}" for name in missing_results] or ["intake did not finish"]
        final = {
            "decision": "Incomplete",
            "status": "Review Required",
            "final_score": None,
            "eligibility": "Not evaluated",
            "justification": ("The application is incomplete, so it was NOT scored and no values were assumed. "
                              "Missing or invalid: " + "; ".join(problems) + ". Please obtain the information and resubmit."),
            "missing_fields": problems,
            "llm_explanation": None,
            "rubric_references": [],
            "tools_used": [],
        }
        self.memory.update(application_id, "final_decision", final)
        input_summary = "Results from earlier agents: " + ("incomplete" if missing_results else "complete")
        output_summary = "Status: Incomplete application - review required. No score calculated."
        self.log.log(application_id, AGENT_NAME, "[fan-in] Incomplete application status",
                     input_summary, output_summary, "incomplete")
        return trace_entry(AGENT_NAME, "[fan-in] Incomplete application status", [],
                           input_summary, output_summary, "incomplete", started)
