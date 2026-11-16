"""Tools used by the Eligibility Agent. Each check returns the same shape of dictionary."""
import config
from tools import format_inr


def _result(rule_id, rule, passed, detail):
    return {"rule_id": rule_id, "rule": rule, "passed": passed, "detail": detail}


def check_cgpa_eligibility(cgpa, min_cgpa):
    """TOOL 1: is the CGPA at least the minimum?"""
    passed = cgpa >= min_cgpa
    detail = f"CGPA {cgpa} {'meets' if passed else 'is below'} the minimum of {min_cgpa}"
    return _result(config.CLAUSE["cgpa"], f"Minimum CGPA of {min_cgpa}", passed, detail)


def check_income_eligibility(income, max_income):
    """TOOL 2: is the family income within the maximum? (exactly the maximum is allowed)"""
    passed = income <= max_income
    detail = (f"Family income {format_inr(income)} is "
              f"{'within' if passed else 'above'} the maximum of {format_inr(max_income)}")
    return _result(config.CLAUSE["income"], f"Maximum annual family income of {format_inr(max_income)}",
                   passed, detail)


def check_course_eligibility(course, eligible_courses):
    """TOOL 3: is the course one of the eligible programmes? ('B.Tech CSE' matches 'B.Tech')"""
    def simple(text):
        return text.lower().replace(".", "").replace(" ", "")
    passed = any(simple(course).startswith(simple(c)) for c in eligible_courses)
    detail = f"Course '{course}' {'is' if passed else 'is not'} an eligible programme"
    return _result(config.CLAUSE["course"], "Eligible course: " + ", ".join(eligible_courses),
                   passed, detail)


def check_mandatory_requirements(statement, min_chars):
    """TOOL 4: a personal statement of the minimum length must be present."""
    length = len((statement or "").strip())
    passed = length >= min_chars
    detail = f"Personal statement has {length} characters (minimum {min_chars})"
    return _result(config.CLAUSE["mandatory"], f"Personal statement of at least {min_chars} characters",
                   passed, detail)
