"""자료 충분도 — '이 해석을 뒷받침하는 자료가 얼마나 있는가'를 만족도(점수)와 분리해 알려준다.

통계적 신뢰도가 아니라 **자료량 안내**다. 근거 없는 "신뢰도 93%" 같은 숫자를 만들지 않기 위해
등급(low/fair/good)만 계산하고, 화면에는 항상 실제 건수와 기준값을 함께 표시한다.
리뷰가 적은 신규 매장을 '낮은 품질'로 분류하지 않는다 — 등급은 점수가 아니라 점수 옆의 주석이다.

기준값은 운영하며 조정할 상수로 분리했다(score.py 가중치와 같은 방식).
"""

from typing import Literal

SufficiencyLevel = Literal["low", "fair", "good"]

SUFFICIENCY_LOW_BELOW = 10  # 분석 리뷰가 이 미만이면 '판단 자료가 적음'
SUFFICIENCY_GOOD_FROM = 30  # 이 이상이면 '자료가 충분한 편'
ISSUE_MIN_RELATED = 3  # 항목 관련 리뷰가 이 미만이면 '반복 여부를 판단하기 이름'
OBSERVATION_MIN_ANALYZED = 5  # 실행 후 분석 리뷰가 이 미만이면 '관측 자료가 아직 적음'


def sufficiency_level(analyzed_cnt: int) -> SufficiencyLevel:
    if analyzed_cnt < SUFFICIENCY_LOW_BELOW:
        return "low"
    if analyzed_cnt >= SUFFICIENCY_GOOD_FROM:
        return "good"
    return "fair"
