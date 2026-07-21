-- 002 — crawl_jobs 에 수집 건수 기록 컬럼 추가.
-- 목적: ① 0건 2연속 자가진단(구조 변경 의심) 판정 ② 크롤 성공률 발표 수치의 원천
--       (ARCHITECTURE.md §5 "세션별 수집 건수 기록"). 기존 마이그레이션은 수정하지 않는다.

alter table crawl_jobs add column if not exists collected int;
