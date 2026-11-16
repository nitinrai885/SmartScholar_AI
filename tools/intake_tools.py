"""Tools used by the Intake Agent."""
import re

import config


def parse_number(value):
    """Turn 8.5, '8.5', '₹2,50,000' or '2.5 lakh' into a float. Returns None if it cannot."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower().replace(",", "")
    if text == "" or re.search(r"-\s*\d", text):      # empty or negative sign
        return None
    match = re.search(r"\d+(?:\.\d+)?", text)
    if match is None:
        return None
    number = float(match.group())
    if "lakh" in text or "lac" in text:
        number *= 100000
    return number


def _clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _numeric_field(value):
    """Parsed number if possible. If the user typed something unreadable we keep the
    original text so the validation tool can report it (we never guess a number)."""
    if _clean_text(value) is None:
        return None
    parsed = parse_number(value)
    return parsed if parsed is not None else str(value).strip()


def _clean_achievements(value):
    """Accept a list or a text block (one per line / comma / semicolon). Remove blanks and duplicates."""
    if value is None:
        return []
    items = value if isinstance(value, list) else re.split(r"[\n;,]", str(value))
    cleaned, seen = [], set()
    for item in items:
        text = str(item).strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            cleaned.append(text)
    return cleaned


def extract_application_details(raw_input):
    """TOOL 1: convert the raw submission into one structured application record."""
    income = _numeric_field(raw_input.get("family_income"))
    if isinstance(income, float) and income.is_integer():
        income = int(income)
    return {
        "application_id": _clean_text(raw_input.get("application_id")),
        "student_name": _clean_text(raw_input.get("student_name")),
        "cgpa": _numeric_field(raw_input.get("cgpa")),
        "family_income": income,
        "course": _clean_text(raw_input.get("course")),
        "achievements": _clean_achievements(raw_input.get("achievements")),
        "statement": _clean_text(raw_input.get("statement") or raw_input.get("personal_statement")),
    }


def validate_application_fields(record):
    """TOOL 2: list missing required fields and invalid values. Nothing is assumed."""
    missing = [name for name in config.REQUIRED_FIELDS if record.get(name) in (None, "")]
    invalid = []
    cgpa = record.get("cgpa")
    if "cgpa" not in missing:
        if not isinstance(cgpa, (int, float)):
            invalid.append("cgpa must be a number")
        elif not 0 <= cgpa <= 10:
            invalid.append("cgpa must be between 0 and 10")
    income = record.get("family_income")
    if "family_income" not in missing:
        if not isinstance(income, (int, float)):
            invalid.append("family_income must be a number")
        elif income < 0:
            invalid.append("family_income cannot be negative")
    return {"valid": not missing and not invalid,
            "missing_fields": missing,
            "invalid_fields": invalid}
