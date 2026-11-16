"""AGENT 2 - Eligibility Agent: checks the mandatory rules and names the exact failed rule."""
import json

from semantic_kernel.functions import kernel_function

import config
from kernel_setup import call_tool
from memory.execution_log import now_iso, trace_entry
from rag.rag_engine import select_references
from tools import eligibility_tools

AGENT_NAME = "Eligibility Agent"
PLUGIN = "EligibilityTools"


class EligibilityTools:
    @kernel_function(name="check_cgpa_eligibility",
                     description="Check that the CGPA is at least the minimum.")
    def check_cgpa_eligibility(self, cgpa: float, min_cgpa: float) -> str:
        return json.dumps(eligibility_tools.check_cgpa_eligibility(cgpa, min_cgpa))

    @kernel_function(name="check_income_eligibility",
                     description="Check that the annual family income is within the maximum.")
    def check_income_eligibility(self, income: float, max_income: float) -> str:
        return json.dumps(eligibility_tools.check_income_eligibility(income, max_income))

    @kernel_function(name="check_course_eligibility",
                     description="Check that the course is an eligible programme.")
    def check_course_eligibility(self, course: str, eligible_courses_json: str) -> str:
        return json.dumps(eligibility_tools.check_course_eligibility(course, json.loads(eligible_courses_json)))

    @kernel_function(name="check_mandatory_requirements",
                     description="Check that a personal statement of the minimum length is present.")
    def check_mandatory_requirements(self, statement: str, min_chars: int) -> str:
        return json.dumps(eligibility_tools.check_mandatory_requirements(statement, min_chars))


class EligibilityAgent:
    def __init__(self, kernel, rag, memory, log):
        self.kernel, self.rag, self.memory, self.log = kernel, rag, memory, log
        kernel.add_plugin(EligibilityTools(), plugin_name=PLUGIN)

    async def run(self, application_id):
        started, tools_used = now_iso(), []
        record = self.memory.get(application_id)
        rules = config.ELIGIBILITY_RULES

        # 1) RAG: fetch the eligibility clauses from the rubric BEFORE judging.
        retrieved = self.rag.retrieve("minimum CGPA, maximum family income, eligible course, mandatory requirements",
                                      sections=["Eligibility"], n_results=5)
        self.log.log(application_id, AGENT_NAME, "RAG retrieval", "Query: eligibility rules",
                     "Retrieved clauses: " + ", ".join(c["clause_id"] for c in retrieved))

        # 2) Run the four deterministic checks through the kernel.
        checks = [
            await call_tool(self.kernel, PLUGIN, "check_cgpa_eligibility", tools_used,
                            cgpa=record["cgpa"], min_cgpa=rules["min_cgpa"]),
            await call_tool(self.kernel, PLUGIN, "check_income_eligibility", tools_used,
                            income=record["family_income"], max_income=rules["max_family_income"]),
            await call_tool(self.kernel, PLUGIN, "check_course_eligibility", tools_used,
                            course=record["course"],
                            eligible_courses_json=json.dumps(rules["eligible_courses"])),
            await call_tool(self.kernel, PLUGIN, "check_mandatory_requirements", tools_used,
                            statement=record["statement"], min_chars=rules["min_statement_chars"]),
        ]

        failed = [f"{c['rule_id']}: {c['rule']} - {c['detail']}" for c in checks if not c["passed"]]
        eligible = not failed
        if eligible:
            reason = "All mandatory eligibility requirements are satisfied."
        else:
            reason = "Failed mandatory eligibility rule(s): " + "; ".join(failed) + ". Recommendation: Reject."

        result = {
            "eligible": eligible,
            "failed_rules": failed,
            "reason": reason,
            "recommendation": "Proceed to scoring" if eligible else "Reject",
            "checks": checks,
            "rubric_references": select_references(retrieved, {c["rule_id"] for c in checks}),
            "tools_used": tools_used,
        }
        self.memory.update(application_id, "eligibility_result", result)

        input_summary = (f"CGPA {record['cgpa']}, income {record['family_income']}, "
                         f"course {record['course']}")
        output_summary = "Eligible: all 4 rules passed" if eligible else f"NOT eligible: {len(failed)} rule(s) failed"
        self.log.log(application_id, AGENT_NAME, "Checked mandatory eligibility rules",
                     input_summary, output_summary)
        return trace_entry(AGENT_NAME, "Checked mandatory eligibility rules", tools_used,
                           input_summary, output_summary, "success", started)
