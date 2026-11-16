"""AGENT 3 - Merit Agent: academic score + achievement score (deterministic) with rubric references."""
import json

from semantic_kernel.functions import kernel_function

import config
from kernel_setup import call_tool
from memory.execution_log import now_iso, trace_entry
from rag.rag_engine import select_references
from tools import merit_tools

AGENT_NAME = "Merit Agent"
PLUGIN = "MeritTools"


class MeritTools:
    @kernel_function(name="calculate_academic_score",
                     description="Academic points (max 70) from the CGPA bands in the rubric.")
    def calculate_academic_score(self, cgpa: float) -> str:
        return json.dumps(merit_tools.calculate_academic_score(cgpa))

    @kernel_function(name="calculate_achievement_score",
                     description="Achievement points (max 30) from a JSON list of achievements.")
    def calculate_achievement_score(self, achievements_json: str) -> str:
        return json.dumps(merit_tools.calculate_achievement_score(json.loads(achievements_json)))


class MeritAgent:
    def __init__(self, kernel, rag, memory, log):
        self.kernel, self.rag, self.memory, self.log = kernel, rag, memory, log
        kernel.add_plugin(MeritTools(), plugin_name=PLUGIN)

    async def run(self, application_id):
        started, tools_used = now_iso(), []
        record = self.memory.get(application_id)

        retrieved = self.rag.retrieve("academic performance CGPA bands and achievement points",
                                      sections=["Academic Merit", "Achievements"], n_results=5)
        self.log.log(application_id, AGENT_NAME, "RAG retrieval", "Query: merit criteria",
                     "Retrieved clauses: " + ", ".join(c["clause_id"] for c in retrieved))

        academic = await call_tool(self.kernel, PLUGIN, "calculate_academic_score", tools_used,
                                   cgpa=record["cgpa"])
        achievement = await call_tool(self.kernel, PLUGIN, "calculate_achievement_score", tools_used,
                                      achievements_json=json.dumps(record["achievements"]))
        total = academic["score"] + achievement["score"]

        explanation = (
            f"CGPA {record['cgpa']} falls in '{academic['band']}' and earns {academic['score']} of "
            f"{academic['max_score']} points ({academic['clause_id']}). "
            f"{achievement['achievements_listed']} achievement(s) listed, {achievement['achievements_counted']} counted at "
            f"{config.POINTS_PER_ACHIEVEMENT} points each = {achievement['score']} of {achievement['max_score']} points "
            f"({achievement['clause_id']}). Total merit score = {total} of 100 ({config.CLAUSE['merit_total']}).")

        applied = {academic["clause_id"], achievement["clause_id"], config.CLAUSE["merit_total"]}
        result = {
            "academic_score": academic["score"],
            "achievement_score": achievement["score"],
            "total_merit_score": total,
            "academic_band": academic["band"],
            "explanation": explanation,
            "rubric_references": select_references(retrieved, applied),
            "tools_used": tools_used,
        }
        self.memory.update(application_id, "merit_result", result)

        input_summary = f"CGPA {record['cgpa']}, {len(record['achievements'])} achievement(s)"
        output_summary = (f"Academic {academic['score']}/70 + achievements {achievement['score']}/30 "
                          f"= merit {total}/100")
        self.log.log(application_id, AGENT_NAME, "[fan-out] Calculated merit score", input_summary, output_summary)
        return trace_entry(AGENT_NAME, "[fan-out] Calculated merit score", tools_used,
                           input_summary, output_summary, "success", started)
