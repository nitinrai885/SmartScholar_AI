"""
config.py - the ONE place where every rule, weight and threshold lives.

If the scholarship rules change, edit the numbers here (and the matching
text in knowledge_base/scholarship_rubric.txt). The test-suite checks that
the two stay consistent.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")          # reads GROQ_API_KEY from a local .env file

# ---------------------------------------------------------------- file paths
RUBRIC_PATH = BASE_DIR / "knowledge_base" / "scholarship_rubric.txt"
MEMORY_PATH = BASE_DIR / "memory" / "applications.json"
LOG_PATH = BASE_DIR / "logs" / "agent_logs.json"

# ---------------------------------------------------------------- LLM (Groq)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"   # Groq's OpenAI-compatible endpoint
# Optional: force one model with GROQ_MODEL in .env. Otherwise the first model
# in this list that your Groq account can actually use is selected at start-up.
GROQ_MODEL = os.getenv("GROQ_MODEL", "")
GROQ_MODEL_PREFERENCE = [
    "llama-3.3-70b-versatile",   # Llama models first (assignment asks for Llama)
    "llama-3.1-8b-instant",
    "openai/gpt-oss-20b",        # fallback if your account no longer has Llama
    "openai/gpt-oss-120b",
]

# ---------------------------------------------------------------- RAG
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ---------------------------------------------------------------- eligibility
ELIGIBILITY_RULES = {
    "min_cgpa": 7.0,
    "max_family_income": 400000,        # rupees per year (4 lakh), inclusive
    "eligible_courses": ["B.Tech"],
    "min_statement_chars": 20,
}
# Fields the intake agent insists on. Achievements are optional.
REQUIRED_FIELDS = ["application_id", "student_name", "cgpa",
                   "family_income", "course", "statement"]

# ---------------------------------------------------------------- merit scoring
# (minimum CGPA, points) - checked from the top, first match wins
ACADEMIC_BANDS = [(9.0, 70), (8.5, 60), (8.0, 50), (7.5, 40), (7.0, 30)]
ACADEMIC_MAX = 70
POINTS_PER_ACHIEVEMENT = 10
ACHIEVEMENT_MAX = 30                    # so at most 3 achievements count

# ---------------------------------------------------------------- need scoring
# (income upper limit, points). Income must be BELOW the limit, except the last
# band which also includes its limit (4,00,000 is still eligible).
NEED_BANDS = [(100000, 100), (200000, 80), (300000, 60), (400000, 40)]
NEED_MAX = 100

# ---------------------------------------------------------------- final decision
WEIGHTS = {"merit": 0.60, "need": 0.40}
THRESHOLDS = {"award": 80, "waitlist": 60}   # >=80 Award, >=60 Waitlist, else Reject

# ---------------------------------------------------------------- rubric clause ids
# These ids must exist in knowledge_base/scholarship_rubric.txt
CLAUSE = {
    "cgpa": "ELG-1", "income": "ELG-2", "course": "ELG-3", "mandatory": "ELG-4",
    "academic": "MER-1", "merit_total": "MER-2", "achievement": "ACH-1",
    "need": "NEED-1", "weights": "WGT-1", "decision": "DEC-1",
}
