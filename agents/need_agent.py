"""AGENT 4 - Need Agent: financial need score (deterministic) with the retrieved rubric criteria."""
import json

from semantic_kernel.functions import kernel_function

from kernel_setup import call_tool
from memory.execution_log import now_iso, trace_entry
from rag.rag_engine import select_references
from tools import need_tools

AGENT_NAME = "Need Agent"
PLUGIN = "NeedTools"


class NeedTools:
    """This plugin holds the RAG engine because one of its tools is a retrieval tool."""

    def __init__(self, rag):
        self.rag = rag

    @kernel_function(name="calculate_financial_need_score",
                     description="Need points (max 100) from the annual family income bands in the rubric.")
    def calculate_financial_need_score(self, income: float) -> str:
        return json.dumps(need_tools.calculate_financial_need_score(income))

    @kernel_function(name="retrieve_financial_need_criteria",
                     description="Retrieve the financial-need clauses of the scholarship rubric (RAG).")
    def retrieve_financial_need_criteria(self, query: str) -> str:
        return json.dumps(need_tools.retrieve_financial_need_criteria(self.rag, query))


class NeedAgent:
    def __init__(self, kernel, rag, memory, log):
        self.kernel, self.memory, self.log = kernel, memory, log
        kernel.add_plugin(NeedTools(rag), plugin_name=PLUGIN)

    async def run(self, application_id):
        started, tools_used = now_iso(), []
        record = self.memory.get(application_id)

        retrieved = await call_tool(self.kernel, PLUGIN, "retrieve_financial_need_criteria", tools_used,
                                    query="family income bands and financial need points")
        self.log.log(application_id, AGENT_NAME, "RAG retrieval", "Query: financial need criteria",
                     "Retrieved clauses: " + ", ".join(c["clause_id"] for c in retrieved))

        need = await call_tool(self.kernel, PLUGIN, "calculate_financial_need_score", tools_used,
                               income=record["family_income"])
        explanation = (f"Annual family income falls in the band '{need['income_band']}', which earns "
                       f"{need['score']} of {need['max_score']} points ({need['clause_id']}).")

        result = {
            "need_score": need["score"],
            "max_score": need["max_score"],
            "income_band": need["income_band"],
            "explanation": explanation,
            "criteria_retrieved": [c["clause_id"] for c in retrieved],
            "rubric_references": select_references(retrieved, {need["clause_id"]}),
            "tools_used": tools_used,
        }
        self.memory.update(application_id, "need_result", result)

        input_summary = f"Annual family income {record['family_income']}"
        output_summary = f"Need score {need['score']}/100 ({need['income_band']})"
        self.log.log(application_id, AGENT_NAME, "[fan-out] Calculated financial need score",
                     input_summary, output_summary)
        return trace_entry(AGENT_NAME, "[fan-out] Calculated financial need score", tools_used,
                           input_summary, output_summary, "success", started)
