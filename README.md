# SmartScholar AI
**AI-Powered Multi-Agent Scholarship Evaluation System** - B.Tech CSE Agentic AI assignment.
*The rubric in `knowledge_base/` is sample demonstration data, not a real university policy.*

## 1. Introduction and objective
SmartScholar AI evaluates a student's scholarship application and returns **Award**, **Waitlist** or **Reject** (or **Incomplete** when information is missing). Five specialised agents collaborate through a **fan-out / fan-in rubric scoring** workflow. Every score is computed by deterministic Python tools and justified with clauses retrieved from the rubric through **RAG**; the LLM is used only for language (a statement summary and a plain-language explanation).

## 2. Agent roster
| Agent | File | Job |
|---|---|---|
| Intake | `agents/intake_agent.py` | Raw form -> structured JSON record; finds missing/invalid fields |
| Eligibility | `agents/eligibility_agent.py` | Mandatory rules (CGPA, income, course, statement); names the exact failed rule |
| Merit | `agents/merit_agent.py` | Academic (max 70) + achievement (max 30) score |
| Need | `agents/need_agent.py` | Financial need score (max 100) from family income |
| Panel Manager | `agents/panel_manager.py` | Weighted score (merit 60%, need 40%), decision, explanation |

## 3. Architecture
<img src="architecture.png" alt="Architecture" width="620">

`coordinator.py` runs: Intake -> Eligibility -> **fan-out** (`asyncio.gather` starts Merit and Need together) -> **fan-in** (Panel Manager starts only after both results are in shared memory). Each agent's tools are registered as **Semantic Kernel plugins** and executed with `kernel.invoke(...)`; LLM calls use `kernel.invoke_prompt(...)` on a Groq chat service.

**Why fan-out / fan-in fits:** merit and need depend on different fields and never on each other, so they can run independently; the decision needs both, so one agent must wait for and combine them. Adding a new rubric criterion means adding one more parallel agent.

## 4. Tools used by each agent
| Agent | Tools (all really executed; see the trace page) |
|---|---|
| Intake | `extract_application_details`, `validate_application_fields` |
| Eligibility | `check_cgpa_eligibility`, `check_income_eligibility`, `check_course_eligibility`, `check_mandatory_requirements` |
| Merit | `calculate_academic_score`, `calculate_achievement_score` |
| Need | `retrieve_financial_need_criteria` (RAG), `calculate_financial_need_score` |
| Panel Manager | `calculate_weighted_score`, `generate_final_decision` |

All rules, bands, weights and thresholds live in `config.py` (nothing hardcoded elsewhere). A test checks that `config.py` and the rubric text agree.

## 5. RAG
`rag/rag_engine.py` splits `scholarship_rubric.txt` into one chunk per clause (`[ELG-1]`, `[MER-1]` ...), embeds them with Sentence Transformers (`all-MiniLM-L6-v2`), stores them in ChromaDB and answers similarity searches (optionally limited to a rubric section). Each agent retrieves its clauses *before* scoring; a rubric reference is attached only if the clause was both **retrieved** and **applied**. If ChromaDB or the embedding model cannot load (e.g. first run offline) a labelled keyword search is used instead; the sidebar shows which mode is active.

## 6. Shared memory and logs
`memory/shared_memory.py` keeps one JSON record per application (`applications.json`). All agents read the same record and write only their own key (`intake_result`, `eligibility_result`, `merit_result`, `need_result`, `final_decision`). Re-submitting an id moves the old evaluation into `previous_evaluations`. `logs/agent_logs.json` is append-only (one JSON object per line, opened in append mode): timestamp, application id, agent, action, input, output, status.

## 7. Failure scenario handled: missing information
If CGPA, income or the statement is blank (or unreadable such as "eight"), Intake flags it, the Eligibility/Merit/Need agents are logged as *skipped*, and the Panel Manager returns **Incomplete - Review Required** with the missing fields. No value is guessed and no score is invented. Also handled: Groq unreachable or model unavailable -> **demo mode** (same scores and decisions, no LLM text); an agent crash -> recorded as an error, never silently ignored.

## 8. Installation (Windows, VS Code)
```
cd SmartScholar_AI
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
Put your key in `.env` (`GROQ_API_KEY=...`, from https://console.groq.com/keys). Without a key the app runs in demo mode. The first run downloads the embedding model (~90 MB).
**Groq model:** at start-up the app asks Groq which models your key can use and picks the first available from `config.GROQ_MODEL_PREFERENCE` (Llama first, then `openai/gpt-oss-*`). Groq's docs list the two Llama models as Enterprise-only after the August 2026 deprecation, so free accounts will usually fall back to `openai/gpt-oss-20b`. Override with `GROQ_MODEL` in `.env`.

## 9. Execution
- Dashboard: `streamlit run app.py`
- Notebook: open `demo.ipynb` in VS Code, choose the `.venv` kernel, **Run All**
- Tests: `python -m pytest -v`
