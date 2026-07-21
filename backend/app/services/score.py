"""종합 평판 점수 산식. 가중치는 상수로 분리(설명 가능·조정 가능).

score = 100 × (0.5·긍정비율 + 0.3·평점정규화 + 0.2·답변율)
(TECH_SPEC §7, BACKEND.md §9 dashboard)
"""

# 가중치 (합 = 1.0)
W_POSITIVE_RATIO = 0.5
W_RATING = 0.3
W_ANSWER_RATE = 0.2
RATING_MAX = 5.0


def composite_score(
    positive_ratio: float, avg_rating: float | None, answer_rate: float
) -> float:
    """0~100 점. positive_ratio·answer_rate 는 0~1, avg_rating 은 0~5(없으면 0 취급)."""
    rating_norm = (avg_rating / RATING_MAX) if avg_rating else 0.0
    raw = (
        W_POSITIVE_RATIO * positive_ratio
        + W_RATING * rating_norm
        + W_ANSWER_RATE * answer_rate
    )
    return round(100 * raw, 1)
