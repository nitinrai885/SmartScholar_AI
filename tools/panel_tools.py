"""Tools used by the Panel Manager. Pure arithmetic and comparisons."""


def calculate_weighted_score(merit_score, need_score, merit_weight, need_weight):
    """TOOL 1: Final Score = Merit x merit_weight + Need x need_weight (rounded to 2 decimals)."""
    if abs(merit_weight + need_weight - 1.0) > 1e-9:
        raise ValueError("Merit and need weights must add up to 1.0")
    final = round(merit_score * merit_weight + need_score * need_weight, 2)
    formula = f"({merit_score} x {merit_weight:.2f}) + ({need_score} x {need_weight:.2f}) = {final}"
    return {"final_score": final, "formula": formula}


def generate_final_decision(final_score, eligible, award_min, waitlist_min):
    """TOOL 2: turn the score into Award / Waitlist / Reject. Failed eligibility always means Reject."""
    if not eligible:
        return {"decision": "Reject", "reason": "Failed a mandatory eligibility rule"}
    if final_score >= award_min:
        return {"decision": "Award", "reason": f"Score {final_score} is {award_min} or more"}
    if final_score >= waitlist_min:
        return {"decision": "Waitlist",
                "reason": f"Score {final_score} is {waitlist_min} or more but below {award_min}"}
    return {"decision": "Reject", "reason": f"Score {final_score} is below {waitlist_min}"}
