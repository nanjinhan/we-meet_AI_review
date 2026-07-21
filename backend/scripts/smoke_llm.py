"""(수동) 실제 리뷰 5건을 분류하는 스모크 스크립트. 실제 GEMINI_API_KEY 필요.

CI/pytest 에서 실행하지 않는다(라이브 API 호출). 로컬에서 프롬프트/게이트웨이 점검용.
실행: cd backend && python -m scripts.smoke_llm
"""

import asyncio

from app.config import settings
from app.llm.client import generate
from app.llm.schemas import BatchAnalysisOut

SAMPLES = [
    "음식은 맛있는데 대기시간이 30분이나 걸려서 너무 힘들었어요.",
    "사장님이 정말 친절하시고 매장도 깨끗해서 기분 좋게 먹고 갑니다!",
    "머리카락이 나왔어요. 위생 관리 좀 제대로 해주세요. 환불 요청합니다.",
    "가격이 좀 있는 편이지만 분위기가 좋아서 데이트하기 괜찮아요.",
    "그냥 평범해요. 다시 올지는 모르겠네요.",
]


async def main() -> None:
    reviews = "\n".join(f"{i}. {body}" for i, body in enumerate(SAMPLES))
    result = await generate(
        "classify_v1",
        {"reviews": reviews},
        BatchAnalysisOut,
        model=settings.llm_model_classify,
    )
    for item in result.results:
        print(item.model_dump_json(indent=2, exclude_none=True))


if __name__ == "__main__":
    asyncio.run(main())
