"""
End-to-end tests. They run the REAL workflow in deterministic demo mode (no LLM),
using temporary memory/log files so your real data is never touched.

Run:  python -m pytest -v
"""
import pytest

import config
from coordinator import Coordinator
from rag.rag_engine import RagEngine
from tools import format_inr, intake_tools, panel_tools


@pytest.fixture(scope="module")
def coordinator(tmp_path_factory):
    folder = tmp_path_factory.mktemp("smartscholar")
    return Coordinator(use_llm=False,
                       memory_path=folder / "applications.json",
                       log_path=folder / "agent_logs.json")


def application(app_id, cgpa, income, achievements=None, course="B.Tech CSE",
                statement="I need financial assistance to continue my education."):
    return {"application_id": app_id, "student_name": "Test Student", "cgpa": cgpa,
            "family_income": income, "course": course,
            "achievements": achievements if achievements is not None else [],
            "statement": statement}


# ------------------------------------------------------------- the three required scenarios
def test_scenario_1_eligible_student(coordinator):
    record = coordinator.evaluate(application("T1", 8.5, 250000, ["Hackathon Winner", "Academic Excellence"]))
    assert record["eligibility_result"]["eligible"] is True
    assert record["eligibility_result"]["failed_rules"] == []
    assert record["merit_result"]["academic_score"] == 60        # CGPA 8.5 band
    assert record["merit_result"]["achievement_score"] == 20     # 2 x 10
    assert record["merit_result"]["total_merit_score"] == 80
    assert record["need_result"]["need_score"] == 60             # income 2,00,000 to 3,00,000
    assert record["final_decision"]["final_score"] == 72.0       # 80*0.6 + 60*0.4
    assert record["final_decision"]["decision"] == "Waitlist"    # 60 <= 72 < 80
    assert record["final_decision"]["eligibility"] == "Passed"
    assert {"ELG-1", "ELG-2", "MER-1", "ACH-1", "NEED-1", "WGT-1", "DEC-1"} <= \
        {r["clause_id"] for r in record["final_decision"]["rubric_references"]}


def test_scenario_2_ineligible_student(coordinator):
    record = coordinator.evaluate(application("T2", 5.5, 250000, ["Hackathon Winner"]))
    assert record["eligibility_result"]["eligible"] is False
    failed = record["eligibility_result"]["failed_rules"]
    assert len(failed) == 1 and failed[0].startswith("ELG-1: Minimum CGPA of 7.0")
    assert "5.5" in failed[0]
    assert record["final_decision"]["decision"] == "Reject"
    assert record["final_decision"]["eligibility"] == "Failed"
    assert "ELG-1" in record["final_decision"]["justification"]


def test_scenario_3_low_financial_need(coordinator):
    record = coordinator.evaluate(application("T3", 9.2, 380000, ["Research Paper"]))
    assert record["eligibility_result"]["eligible"] is True
    assert record["merit_result"]["total_merit_score"] == 80     # 70 + 10
    assert record["need_result"]["need_score"] == 40             # 3 to 4 lakh
    assert record["final_decision"]["final_score"] == 64.0       # 48 + 16
    assert record["final_decision"]["decision"] == "Waitlist"


# ------------------------------------------------------------- missing information
def test_missing_information_is_not_assumed(coordinator):
    raw = {"application_id": "T4", "student_name": "No Numbers", "course": "B.Tech CSE"}
    record = coordinator.evaluate(raw)
    assert record["intake_result"]["valid"] is False
    assert {"cgpa", "family_income", "statement"} <= set(record["intake_result"]["missing_fields"])
    assert record["eligibility_result"] == {} and record["merit_result"] == {} and record["need_result"] == {}
    assert record["final_decision"]["decision"] == "Incomplete"
    assert record["final_decision"]["final_score"] is None
    assert [t["status"] for t in record["execution_trace"][1:4]] == ["skipped"] * 3


def test_unreadable_number_is_flagged_not_guessed(coordinator):
    record = coordinator.evaluate(application("T5", "eight point five", 250000))
    assert record["final_decision"]["decision"] == "Incomplete"
    assert "cgpa must be a number" in record["intake_result"]["invalid_fields"]


# ------------------------------------------------------------- other decisions and rules
def test_award_decision(coordinator):
    record = coordinator.evaluate(application("T6", 9.5, 80000, ["A", "B", "C"]))
    assert record["merit_result"]["total_merit_score"] == 100
    assert record["need_result"]["need_score"] == 100
    assert record["final_decision"]["final_score"] == 100.0
    assert record["final_decision"]["decision"] == "Award"


def test_reject_decision_for_low_score(coordinator):
    record = coordinator.evaluate(application("T7", 7.0, 400000))     # eligible, lowest bands
    assert record["eligibility_result"]["eligible"] is True            # exactly 4,00,000 is allowed
    assert record["final_decision"]["final_score"] == 34.0             # 30*0.6 + 40*0.4
    assert record["final_decision"]["decision"] == "Reject"


def test_income_and_course_rules(coordinator):
    record = coordinator.evaluate(application("T8", 9.0, 450000, course="M.Tech"))
    failed = " ".join(record["eligibility_result"]["failed_rules"])
    assert "ELG-2" in failed and "ELG-3" in failed and "ELG-1" not in failed
    assert record["need_result"]["need_score"] == 0
    assert record["final_decision"]["decision"] == "Reject"


def test_every_working_agent_used_at_least_two_tools(coordinator):
    record = coordinator.evaluate(application("T9", 8.0, 150000, ["X"]))
    for entry in record["execution_trace"]:
        assert len(entry["tools_used"]) >= 2, entry["agent"]
    assert [t["agent"] for t in record["execution_trace"]] == [
        "Intake Agent", "Eligibility Agent", "Merit Agent", "Need Agent", "Panel Manager"]


def test_fan_in_waits_for_both_fan_out_agents(coordinator):
    trace = coordinator.evaluate(application("T10", 8.0, 150000))["execution_trace"]
    merit, need, panel = trace[2], trace[3], trace[4]
    assert merit["finished"] <= panel["started"] and need["finished"] <= panel["started"]


# ------------------------------------------------------------- memory and logs
def test_shared_memory_keeps_history(coordinator):
    coordinator.evaluate(application("T11", 8.0, 150000))
    record = coordinator.evaluate(application("T11", 9.5, 80000, ["A", "B", "C"]))
    assert len(record["previous_evaluations"]) == 1
    assert record["previous_evaluations"][0]["cgpa"] == 8.0
    assert record["cgpa"] == 9.5


def test_log_is_append_only(coordinator):
    before = coordinator.log.read_all()
    coordinator.evaluate(application("T12", 8.0, 150000))
    after = coordinator.log.read_all()
    assert len(after) > len(before)
    assert after[:len(before)] == before                               # old lines untouched
    fields = {"timestamp", "application_id", "agent", "action", "input_summary", "output_summary", "status"}
    assert fields <= set(after[-1])


# ------------------------------------------------------------- tools, RAG and rubric consistency
def test_weighted_formula_and_thresholds():
    assert panel_tools.calculate_weighted_score(85, 80, 0.60, 0.40)["final_score"] == 83.0
    for score, expected in [(100, "Award"), (80, "Award"), (79.99, "Waitlist"),
                            (60, "Waitlist"), (59.99, "Reject"), (0, "Reject")]:
        assert panel_tools.generate_final_decision(score, True, 80, 60)["decision"] == expected
    assert panel_tools.generate_final_decision(99, False, 80, 60)["decision"] == "Reject"


def test_number_parsing_helpers():
    assert intake_tools.parse_number("₹2,50,000") == 250000
    assert intake_tools.parse_number("2.5 lakh") == 250000
    assert intake_tools.parse_number("-5") is None
    assert format_inr(250000) == "₹2,50,000"


def test_rubric_matches_config_and_rag_finds_clauses():
    engine = RagEngine()
    ids = {chunk["clause_id"] for chunk in engine.chunks}
    assert set(config.CLAUSE.values()) <= ids                         # every clause id used in code exists
    text = config.RUBRIC_PATH.read_text(encoding="utf-8")
    for needed in ["7.0", "4,00,000", "0.60", "0.40", "10 points", "Rs 1,00,000", "80 or more", "60 or more"]:
        assert needed in text
    top = engine.retrieve("What is the minimum CGPA requirement?", sections=["Eligibility"], n_results=2)
    assert "ELG-1" in [c["clause_id"] for c in top]
    assert engine.retrieve("family income points", sections=["Financial Need"])[0]["clause_id"] == "NEED-1"
