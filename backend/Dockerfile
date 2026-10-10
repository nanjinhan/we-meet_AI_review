# api용 — uvicorn만 돈다. 크롤러(Playwright)는 포함하지 않는다(Dockerfile.worker가 담당).
# (T-15, ARCHITECTURE.md §2/§5 — docker-compose.yml: api + worker + caddy)
FROM python:3.12-slim

WORKDIR /app

# asyncpg/psycopg류 빌드에 필요한 최소 OS 패키지만. 빌드 후 캐시 정리로 이미지 크기 절약.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 의존성 레이어를 코드보다 먼저 복사해 캐시 적중률을 높인다.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir -e .

# migrations/prompts/selectors는 코드가 런타임에 읽는다 (prompts: llm/client.py, selectors: naver.py)
COPY migrations ./migrations
COPY prompts ./prompts
COPY selectors.yaml ./selectors.yaml
# scripts/seed_demo.py — 데모 시드를 `docker compose exec api python -m scripts.seed_demo`로 실행하기 위함
COPY scripts ./scripts

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
