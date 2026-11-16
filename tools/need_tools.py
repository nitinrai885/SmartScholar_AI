"""Tools used by the Need Agent."""
import config
from tools import format_inr


def calculate_financial_need_score(income):
    """TOOL 1: need points (max 100) from the income bands in rubric clause NEED-1."""
    bands = config.NEED_BANDS
    lower = 0
    for index, (limit, points) in enumerate(bands):
        is_last = index == len(bands) - 1
        if income < limit or (is_last and income == limit):
            if lower == 0:
                band = f"below {format_inr(limit)}"
            elif is_last:
                band = f"{format_inr(lower)} to {format_inr(limit)} (inclusive)"
            else:
                band = f"{format_inr(lower)} to below {format_inr(limit)}"
            return {"score": points, "max_score": config.NEED_MAX,
                    "income_band": band, "clause_id": config.CLAUSE["need"]}
        lower = limit
    return {"score": 0, "max_score": config.NEED_MAX,
            "income_band": f"above {format_inr(bands[-1][0])}", "clause_id": config.CLAUSE["need"]}


def retrieve_financial_need_criteria(rag, query):
    """TOOL 2: ask the RAG engine for the financial-need clauses of the rubric."""
    return rag.retrieve(query, sections=["Financial Need"], n_results=3)
