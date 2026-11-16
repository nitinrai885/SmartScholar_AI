"""AGENT 1 - Intake Agent: raw application -> structured, validated record."""
import json

from semantic_kernel.functions import kernel_function

from kernel_setup import ask_llm, call_tool, clean_for_prompt
from memory.execution_log import now_iso, trace_entry
from tools import intake_tools

AGENT_NAME = "Intake Agent"
PLUGIN = "IntakeTools"


class IntakeTools:
    """Semantic Kernel plugin: wraps the plain Python tools so the kernel can run them."""

    @kernel_function(name="extract_application_details",
                     description="Convert the raw application (JSON text) into a structured record.")
    def extract_application_details(self, raw_json: str) -> str:
        return json.dumps(intake_tools.extract_application_details(json.loads(raw_json)))

    @kernel_function(name="validate_application_fields",
                     description="Find missing or invalid fields in a structured record (JSON text).")
    def validate_application_fields(self, record_json: str) -> str:
        return json.dumps(intake_tools.validate_application_fields(json.loads(record_json)))


class IntakeAgent:
    def __init__(self, kernel, memory, log, llm_on):
        self.kernel, self.memory, self.log, self.llm_on = kernel, memory, log, llm_on
        kernel.add_plugin(IntakeTools(), plugin_name=PLUGIN)

    async def run(self, application_id, raw_input):
        started, tools_used = now_iso(), []

        record = await call_tool(self.kernel, PLUGIN, "extract_application_details", tools_used,
                                 raw_json=json.dumps(raw_input, default=str))
        validation = await call_tool(self.kernel, PLUGIN, "validate_application_fields", tools_used,
                                     record_json=json.dumps(record))

        # LLM use (optional): a one-sentence summary of the personal statement.
        summary = None
        if validation["valid"] and self.llm_on:
            prompt = ("Summarise this scholarship personal statement in one sentence of at most 25 words. "
                      "Use only what the student wrote and add no new facts.\n\nStatement: "
                      + clean_for_prompt(record["statement"]))
            summary = await ask_llm(self.kernel, prompt)
        validation["llm_used"] = summary is not None

        fields = {k: v for k, v in record.items() if k != "application_id"}
        fields["statement_summary"] = summary
        fields["intake_result"] = validation
        self.memory.update_many(application_id, fields)

        input_summary = f"Raw fields received: {', '.join(sorted(raw_input.keys())) or 'none'}"
        if validation["valid"]:
            output_summary = "Structured record created. All required fields present and valid."
            status = "success"
        else:
            problems = validation["missing_fields"] + validation["invalid_fields"]
            output_summary = "INCOMPLETE application. Missing/invalid: " + "; ".join(problems)
            status = "incomplete"
        self.log.log(application_id, AGENT_NAME, "Extracted and validated application",
                     input_summary, output_summary, status)
        return trace_entry(AGENT_NAME, "Extracted and validated application", tools_used,
                           input_summary, output_summary, status, started)
