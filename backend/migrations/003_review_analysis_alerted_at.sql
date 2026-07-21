-- 003 — review_analysis 에 알림 발송 시각 추가.
-- 목적: 다이제스트(1시간 묶음) 중복 발송 방지. 미발송 = null, 발송 시 now() 기록.
-- 긴급 즉시 발송·다이제스트 모두 이 컬럼으로 '이미 알림 보냄'을 판정한다.

alter table review_analysis add column if not exists alerted_at timestamptz;
