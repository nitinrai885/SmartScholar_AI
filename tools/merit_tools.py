"""Tools used by the Merit Agent. Scores come from the bands in config.py, never from the LLM."""
import config


def calculate_academic_score(cgpa):
    """TOOL 1: academic points (max 70) from the CGPA bands in rubric clause MER-1."""
    bands = config.ACADEMIC_BANDS
    for index, (minimum, points) in enumerate(bands):
        if cgpa >= minimum:
            if index == 0:
                band = f"CGPA {minimum} and above"
            else:
                band = f"CGPA {minimum} to below {bands[index - 1][0]}"
            return {"score": points, "max_score": config.ACADEMIC_MAX,
                    "band": band, "clause_id": config.CLAUSE["academic"]}
    return {"score": 0, "max_score": config.ACADEMIC_MAX,
            "band": f"CGPA below {bands[-1][0]}", "clause_id": config.CLAUSE["academic"]}


def calculate_achievement_score(achievements):
    """TOOL 2: achievement points (max 30) from rubric clause ACH-1."""
    count = len(achievements)
    max_counted = config.ACHIEVEMENT_MAX // config.POINTS_PER_ACHIEVEMENT
    counted = min(count, max_counted)
    return {"score": counted * config.POINTS_PER_ACHIEVEMENT, "max_score": config.ACHIEVEMENT_MAX,
            "achievements_listed": count, "achievements_counted": counted,
            "clause_id": config.CLAUSE["achievement"]}
