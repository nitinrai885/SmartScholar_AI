"""
Semantic Kernel helpers shared by all agents.

* check_groq_model()  - asks Groq which models your key can use and picks one.
* build_kernel()      - creates a Semantic Kernel Kernel (with a Groq chat service if available).
* call_tool()         - runs a Python tool THROUGH the kernel (kernel.invoke) and records it.
* ask_llm()           - sends a prompt to the LLM through the kernel (kernel.invoke_prompt).
"""
import json

from semantic_kernel import Kernel

import config


def check_groq_model():
    """Return (ok, model_id, message). Never raises: any problem just means 'use demo mode'."""
    if not config.GROQ_API_KEY:
        return False, None, "GROQ_API_KEY is not set (see .env.example)"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.GROQ_API_KEY, base_url=config.GROQ_BASE_URL,
                        timeout=10, max_retries=0)
        available = {model.id for model in client.models.list().data}
    except Exception as error:
        return False, None, f"Could not reach Groq: {type(error).__name__}: {error}"
    candidates = [config.GROQ_MODEL] if config.GROQ_MODEL else config.GROQ_MODEL_PREFERENCE
    for model_id in candidates:
        if model_id in available:
            return True, model_id, f"Using Groq model '{model_id}'"
    return False, None, ("None of these models are available to your Groq key: "
                         + ", ".join(candidates) + ". Set GROQ_MODEL in .env to one from "
                         "https://console.groq.com/docs/models")


def build_kernel(model_id=None):
    """A Kernel always exists (tools run through it). The chat service is added only if model_id is given."""
    kernel = Kernel()
    if model_id:
        from openai import AsyncOpenAI
        from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
        client = AsyncOpenAI(api_key=config.GROQ_API_KEY, base_url=config.GROQ_BASE_URL)
        kernel.add_service(OpenAIChatCompletion(service_id="groq", ai_model_id=model_id,
                                                async_client=client))
    return kernel


async def call_tool(kernel, plugin_name, function_name, tools_used, **arguments):
    """Run one registered tool through the kernel, remember that it ran, return its output as a dict/list."""
    result = await kernel.invoke(plugin_name=plugin_name, function_name=function_name, **arguments)
    tools_used.append(function_name)
    return json.loads(str(result))


def clean_for_prompt(text):
    """Semantic Kernel prompts treat curly braces specially, so remove them from user text."""
    return str(text).replace("{", "(").replace("}", ")")


async def ask_llm(kernel, prompt):
    """Ask the LLM. Returns None if the API fails, so the project keeps working without it."""
    try:
        result = await kernel.invoke_prompt(prompt=prompt)
        return str(result).strip() or None
    except Exception:
        return None
