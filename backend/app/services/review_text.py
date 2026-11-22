"""리뷰 본문 텍스트 유틸 — 순수 함수(DB·LLM 무관, 단위 테스트 대상).

- verify_quote: LLM 이 준 근거 문장이 리뷰 원문에 실제로 있는지 대조한다. 통과하면 **원문 그대로의
  조각**을 돌려주고, 없으면 None. 리포트의 수치 검증(report_gen._verify)과 같은 원칙 —
  원문에 없는 인용은 화면에 내보내지 않는다.
- normalize_text / long_units: 같은 문장이 여러 리뷰에 반복되는지 찾기 위한 정규화·분리.
"""

import re
import unicodedata

MIN_QUOTE_LEN = 2  # 한 글자짜리 인용("맛")은 근거로서 의미가 없어 버린다
_MAX_FUZZY_QUOTE_LEN = 300  # 이보다 긴 인용은 공백 무시 대조를 하지 않는다(정확히 일치할 때만 통과)

_QUOTE_MARKS = "\"'“”‘’「」『』`"
_EDGE_PUNCT = " \t\r\n.!?~…,·"


def verify_quote(body: str, quote: str | None) -> str | None:
    """quote 가 body 안에 실제로 있으면 원문 조각을, 없으면 None 을 반환.

    따옴표·양끝 문장부호·공백 차이(줄바꿈, 연속 공백, 띄어쓰기 유무)는 허용한다.
    글자가 바뀐 의역·요약은 통과하지 못한다.
    """
    if not quote or not body:
        return None
    q = quote.strip().strip(_QUOTE_MARKS).strip()
    if len(q) >= MIN_QUOTE_LEN and q in body:
        return q

    q = q.strip(_EDGE_PUNCT)
    if len(q) < MIN_QUOTE_LEN:
        return None
    if q in body:
        return q
    if len(q) > _MAX_FUZZY_QUOTE_LEN:
        return None

    # 공백만 다른 경우: 글자 사이에 임의의 공백을 허용해 원문에서 같은 구간을 되찾는다.
    chars = [ch for ch in q if not ch.isspace()]
    if len(chars) < MIN_QUOTE_LEN:
        return None
    match = re.search(r"\s*".join(re.escape(ch) for ch in chars), body)
    return match.group(0) if match else None


def _is_jamo(ch: str) -> bool:
    """낱자모(ㅋㅋ, ㅠㅠ 등) — 문장 비교에서는 잡음이라 뺀다."""
    code = ord(ch)
    return (
        0x1100 <= code <= 0x11FF
        or 0x3130 <= code <= 0x318F
        or 0xA960 <= code <= 0xA97F
        or 0xD7B0 <= code <= 0xD7FF
    )


def normalize_text(text: str) -> str:
    """비교용 정규화: 소문자 + 글자·숫자만 남긴다(공백·문장부호·이모지·낱자모 제거)."""
    lowered = unicodedata.normalize("NFKC", text).lower()  # 전각 문자·분해된 한글도 같은 글자로
    return "".join(ch for ch in lowered if ch.isalnum() and not _is_jamo(ch))


_SENTENCE_SPLIT = re.compile(r"[.!?…\r\n]+")


def split_sentences(body: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(body) if s.strip()]


def long_units(body: str, min_len: int) -> list[tuple[str, str]]:
    """본문에서 '반복 여부를 비교할 단위'를 뽑는다: [(정규화 키, 원문 조각)].

    단위 = 정규화 길이가 min_len 이상인 문장들 + (문장이 여럿이면) 본문 전체.
    짧고 흔한 표현("맛있어요")은 서로 다른 고객이 똑같이 쓸 수 있어 비교 대상에서 뺀다.
    """
    units: dict[str, str] = {}
    sentences = split_sentences(body)
    for sentence in sentences:
        key = normalize_text(sentence)
        if len(key) >= min_len:
            units.setdefault(key, sentence)
    if len(sentences) > 1:
        key = normalize_text(body)
        if len(key) >= min_len:
            units.setdefault(key, body.strip())
    return list(units.items())
