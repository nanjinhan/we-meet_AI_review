-- 004 — 근거 진단: 리뷰 '분석 제외' 표시 + 실행 과제 기록.
--
-- 1) reviews.excluded_at / exclude_reason
--    점주가 검토 후 '분석에서 제외'한 리뷰(중복 수집 등)와 그 이유. null = 분석에 포함.
--    자동 제외는 하지 않는다 — 사람이 결정하고 이유를 남긴다(독립적인 고객 의견을 잘못 지우지 않기 위해).
--    제외된 리뷰는 weekly_aspect_stats 집계에서 빠지고, 화면에는 '제외 N건'으로 항상 표시된다.
--
-- 2) action_items
--    반복 문제(또는 강점)를 근거와 함께 본 뒤 점주가 고른 실행 과제. started_on(실행일)이
--    '이후 리뷰에서 같은 문제가 어떻게 나타나는지' 관측하는 기준점이 된다.
--    관측값(실행 전/후 건수)은 저장하지 않고 조회 시 리뷰에서 다시 센다.

alter table reviews add column if not exists excluded_at timestamptz;
alter table reviews add column if not exists exclude_reason text;

create table if not exists action_items (
  id            bigint generated always as identity primary key,
  store_id      bigint not null references stores(id) on delete cascade,
  aspect        text not null,                 -- 대상 항목 (맛/친절/청결/대기시간/가격/분위기/기타)
  polarity      text not null default 'neg' check (polarity in ('pos','neg')),
  title         text not null,                 -- 실행할 행동 (점주 입력)
  note          text,
  started_on    date not null,                 -- 실행일 — 이후 리뷰 관측의 기준
  status        text not null default 'active' check (status in ('active','done','dropped')),
  created_at    timestamptz default now()
);
create index if not exists idx_action_items_store on action_items(store_id, started_on desc);

alter table action_items enable row level security;
