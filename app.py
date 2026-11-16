"""SmartScholar AI - Streamlit dashboard.  Run with:  streamlit run app.py"""
import html

import pandas as pd
import streamlit as st

from coordinator import Coordinator

st.set_page_config(page_title="SmartScholar AI", page_icon="🎓", layout="wide")

PAGES = ["Dashboard", "New Application", "Evaluation Results", "Agent Execution Trace", "Application History"]
DECISION_COLORS = {"Award": "#1B7F5C", "Waitlist": "#B7791F", "Reject": "#B23A48",
                   "Incomplete": "#5B6770", "Error": "#5B6770"}
STATUS_ICONS = {"success": "✅", "incomplete": "⚠️", "skipped": "⏭️", "error": "❌"}

st.markdown("""
<style>
.decision {padding: 1rem 1.25rem; background: rgba(128,128,128,0.08); border-radius: 6px; margin: .5rem 0 1rem;}
.decision .label {font-size: .85rem; opacity: .7;}
.decision .value {font-size: 2.2rem; font-weight: 700; line-height: 1.2;}
.decision .sub {opacity: .8;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource(show_spinner="Starting agents, loading the rubric and the embedding model...")
def get_coordinator():
    return Coordinator()


try:
    coordinator = get_coordinator()
except Exception as error:                      # clear message instead of a stack trace
    st.error(f"SmartScholar AI could not start: {error}")
    st.stop()

# ------------------------------------------------------------------ sample data for quick demos
SAMPLES = {
    "Eligible student": {"f_id": "SCH001", "f_name": "Rahul Sharma", "f_cgpa": "8.5", "f_income": "250000",
                         "f_course": "B.Tech CSE", "f_ach": "Hackathon Winner\nAcademic Excellence",
                         "f_stmt": "I need financial assistance to continue my education."},
    "Ineligible student": {"f_id": "SCH002", "f_name": "Asha Verma", "f_cgpa": "5.5", "f_income": "250000",
                           "f_course": "B.Tech CSE", "f_ach": "Coding Club Member",
                           "f_stmt": "I would like support to complete my degree."},
    "Low financial need": {"f_id": "SCH003", "f_name": "Kabir Singh", "f_cgpa": "9.2", "f_income": "380000",
                           "f_course": "B.Tech CSE", "f_ach": "Research Paper",
                           "f_stmt": "A scholarship would help me focus on my research projects."},
    "Missing information": {"f_id": "SCH004", "f_name": "Neha Gupta", "f_cgpa": "", "f_income": "",
                            "f_course": "B.Tech CSE", "f_ach": "", "f_stmt": ""},
}
FORM_DEFAULTS = {"f_id": "", "f_name": "", "f_cgpa": "", "f_income": "", "f_course": "B.Tech CSE",
                 "f_ach": "", "f_stmt": ""}
for key, value in FORM_DEFAULTS.items():
    st.session_state.setdefault(key, value)


def load_sample(name):
    for key, value in SAMPLES[name].items():
        st.session_state[key] = value


# ------------------------------------------------------------------ helpers
def show(value, suffix=""):
    return "—" if value in (None, "") else f"{value}{suffix}"


def pick_application(key):
    records = coordinator.memory.all_applications()
    if not records:
        st.info("No applications yet. Submit one from the New Application page.")
        return None
    ids = [r["application_id"] for r in records]
    last = st.session_state.get("last_app_id")
    chosen = st.selectbox("Application", ids, index=ids.index(last) if last in ids else 0, key=key)
    st.session_state["last_app_id"] = chosen
    return next(r for r in records if r["application_id"] == chosen)


def references_table(references):
    if references:
        st.dataframe(pd.DataFrame(references).rename(columns={"clause_id": "Clause", "section": "Section",
                                                              "title": "Rubric clause"}),
                     hide_index=True)
    else:
        st.caption("No rubric clauses were applied (the application was not scored).")


def show_results(record):
    final = record["final_decision"]
    if not final:
        st.warning("This application has no final decision yet.")
        return
    decision = final["decision"]
    color = DECISION_COLORS.get(decision, "#5B6770")
    sub = (f"Final weighted score {final['final_score']} / 100" if final.get("final_score") is not None
           else html.escape(str(final.get("status", ""))))
    st.markdown(f"<div class='decision' style='border-left: 8px solid {color}'>"
                f"<div class='label'>Final decision for {html.escape(record['application_id'])}</div>"
                f"<div class='value' style='color:{color}'>{html.escape(decision)}</div>"
                f"<div class='sub'>{sub}</div></div>", unsafe_allow_html=True)

    merit, need = record["merit_result"], record["need_result"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Eligibility", final.get("eligibility", "—"))
    c2.metric("Merit score", show(merit.get("total_merit_score"), " / 100"))
    c3.metric("Financial need score", show(need.get("need_score"), " / 100"))
    c4.metric("Weighted final score", show(final.get("final_score"), " / 100"))
    if merit and need and final.get("final_score") is not None:
        st.progress(merit["total_merit_score"] / 100, text=f"Merit {merit['total_merit_score']}/100 (weight 60%)")
        st.progress(need["need_score"] / 100, text=f"Financial need {need['need_score']}/100 (weight 40%)")
        st.progress(final["final_score"] / 100, text=f"Final score {final['final_score']}/100")

    st.subheader("Explanation")
    st.write(final["justification"])
    if final.get("llm_explanation"):
        st.info("**Plain-language summary written by the LLM** (numbers above come from Python tools, not the LLM):\n\n"
                + final["llm_explanation"])
    if record["statement_summary"]:
        st.caption("LLM summary of the personal statement: " + record["statement_summary"])

    if merit or need:
        with st.expander("How each score was calculated"):
            if merit:
                st.write("**Merit:** " + merit["explanation"])
            if need:
                st.write("**Financial need:** " + need["explanation"])
            if final.get("formula"):
                st.write("**Weighted score:** " + final["formula"])
    if final.get("failed_rules"):
        st.error("Failed eligibility rules:\n\n" + "\n".join(f"- {rule}" for rule in final["failed_rules"]))
    if final.get("missing_fields"):
        st.warning("Missing or invalid information:\n\n" + "\n".join(f"- {item}" for item in final["missing_fields"]))

    st.subheader("Rubric references")
    st.caption("Clauses come from knowledge_base/scholarship_rubric.txt (sample demonstration data, not a real policy).")
    references_table(final.get("rubric_references", []))


# ------------------------------------------------------------------ sidebar and header
if "goto" in st.session_state:                  # lets other pages jump to a page before the radio is drawn
    st.session_state["page"] = st.session_state.pop("goto")

st.sidebar.title("🎓 SmartScholar AI")
page = st.sidebar.radio("Navigate", PAGES, key="page")
st.sidebar.divider()
st.sidebar.caption("**Mode:** " + coordinator.mode)
if not coordinator.llm_on:
    st.sidebar.caption(coordinator.llm_message)
st.sidebar.caption("**RAG:** " + coordinator.rag.mode)
if coordinator.rag.fallback_reason:
    st.sidebar.caption("Vector search unavailable: " + coordinator.rag.fallback_reason[:150])

st.title("SMARTSCHOLAR AI")
st.caption("AI-Powered Multi-Agent Scholarship Evaluation System")

# ------------------------------------------------------------------ pages
if page == "Dashboard":
    records = coordinator.memory.all_applications()
    decisions = [r["final_decision"].get("decision") for r in records if r["final_decision"]]
    counts = {name: decisions.count(name) for name in ("Award", "Waitlist", "Reject", "Incomplete")}
    cols = st.columns(5)
    cols[0].metric("Total applications", len(records))
    cols[1].metric("Awarded", counts["Award"])
    cols[2].metric("Waitlisted", counts["Waitlist"])
    cols[3].metric("Rejected", counts["Reject"])
    cols[4].metric("Incomplete", counts["Incomplete"])
    if records:
        st.subheader("Decisions")
        st.bar_chart(pd.Series(counts, name="Applications"))
        st.subheader("Latest applications")
        latest = [{"ID": r["application_id"], "Student": r["student_name"] or "—",
                   "Decision": r["final_decision"].get("decision", "—"),
                   "Final score": r["final_decision"].get("final_score"), "Submitted": r["submitted_at"]}
                  for r in records[:5]]
        st.dataframe(pd.DataFrame(latest), hide_index=True)
    else:
        st.info("No applications yet. Open **New Application** and submit one (or load a sample).")

elif page == "New Application":
    st.subheader("New Application")
    st.caption("Load a sample to try the four demo cases, or type your own. Leave a field blank to test missing-information handling.")
    sample_cols = st.columns(len(SAMPLES))
    for col, name in zip(sample_cols, SAMPLES):
        col.button(name, on_click=load_sample, args=(name,))

    with st.form("application_form"):
        left, right = st.columns(2)
        name = left.text_input("Student Name", key="f_name")
        app_id = right.text_input("Application ID", key="f_id")
        cgpa = left.text_input("CGPA (out of 10)", key="f_cgpa")
        income = right.text_input("Annual Family Income (₹)", key="f_income")
        course = left.text_input("Course", key="f_course")
        achievements = st.text_area("Achievements (one per line)", key="f_ach")
        statement = st.text_area("Personal Statement", key="f_stmt")
        submitted = st.form_submit_button("Submit Application", type="primary")

    if submitted:
        raw = {"application_id": app_id, "student_name": name, "cgpa": cgpa, "family_income": income,
               "course": course, "achievements": achievements, "statement": statement}
        try:
            with st.spinner("The five agents are evaluating the application..."):
                record = coordinator.evaluate(raw)
        except Exception as error:
            st.error(f"The evaluation failed: {type(error).__name__}: {error}")
        else:
            st.session_state["last_app_id"] = record["application_id"]
            st.session_state["goto"] = "Evaluation Results"
            st.rerun()

elif page == "Evaluation Results":
    st.subheader("Evaluation Results")
    record = pick_application("results_pick")
    if record:
        show_results(record)

elif page == "Agent Execution Trace":
    st.subheader("Agent Execution Trace")
    record = pick_application("trace_pick")
    if record:
        trace = record["execution_trace"]
        if not trace:
            st.info("No trace was recorded for this application.")
        else:
            st.caption("Merit Agent and Need Agent were started together (fan-out). "
                       "The Panel Manager started only after both had finished (fan-in).")
        for number, step in enumerate(trace, start=1):
            icon = STATUS_ICONS.get(step["status"], "•")
            with st.expander(f"{number}. {step['agent']}  {icon} {step['status']}", expanded=True):
                st.write(f"**What it did:** {step['action']}")
                st.write(f"**Input:** {step['input_summary']}")
                st.write(f"**Output:** {step['output_summary']}")
                tools = ", ".join(f"`{t}`" for t in step["tools_used"]) or "none"
                st.write(f"**Tools actually called:** {tools}")
                st.caption(f"{step['started']}  →  {step['finished']}")
        entries = coordinator.log.read_all(record["application_id"])
        if entries:
            st.subheader("Execution log (append-only)")
            st.dataframe(pd.DataFrame(entries), hide_index=True)

elif page == "Application History":
    st.subheader("Application History")
    records = coordinator.memory.all_applications()
    if not records:
        st.info("No applications yet.")
    else:
        rows = []
        for r in records:
            final = r["final_decision"]
            rows.append({"ID": r["application_id"], "Student": r["student_name"] or "—",
                         "Course": r["course"] or "—", "CGPA": r["cgpa"], "Family income": r["family_income"],
                         "Eligibility": final.get("eligibility", "—"),
                         "Merit": r["merit_result"].get("total_merit_score"),
                         "Need": r["need_result"].get("need_score"),
                         "Final score": final.get("final_score"), "Decision": final.get("decision", "—"),
                         "Earlier evaluations": len(r["previous_evaluations"]),
                         "Submitted": r["submitted_at"]})
        st.dataframe(pd.DataFrame(rows), hide_index=True)

        with_history = [r for r in records if r["previous_evaluations"]]
        if with_history:
            st.subheader("Earlier evaluations of re-submitted applications")
            chosen = st.selectbox("Application", [r["application_id"] for r in with_history])
            record = next(r for r in with_history if r["application_id"] == chosen)
            earlier = [{"Submitted": p["submitted_at"], "CGPA": p["cgpa"], "Family income": p["family_income"],
                        "Final score": p["final_decision"].get("final_score"),
                        "Decision": p["final_decision"].get("decision", "—")}
                       for p in record["previous_evaluations"]]
            st.dataframe(pd.DataFrame(earlier), hide_index=True)
