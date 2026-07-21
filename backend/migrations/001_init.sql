-- =============================================================================
-- 001_init — 초기 스키마. 원본: docs/schema.sql (1:1). 기존 마이그레이션 수정 금지.
-- 로컬 개발에서는 000_dev_auth_stub.sql 을 먼저 적용할 것.
-- =============================================================================

create extension if not exists vector;

-- ---------- 매장 ----------
create table stores (
  id            bigint generated always as identity primary key,
  owner_id      uuid not null,                 -- Supabase auth.users(id). 로컬은 FK 없이 uuid만
  name          text not null,
  category      text,                          -- 카페/식당/미용실
  address       text,
  created_at    timestamptz default now()
);
create index idx_stores_owner on stores(owner_id);

-- 톤 프로필 등 매장별 설정 (스펙 §5.2 few-shot 원천)
create table store_settings (
  store_id      bigint primary key references stores(id) on delete cascade,
  tone_examples jsonb default '[]',            -- ["기존 답글1", "기존 답글2", ...] 3~5개
  default_tone  text default 'polite' check (default_tone in ('polite','friendly','apologetic')),
  notify_urgent boolean default true,
  notify_digest boolean default true,
  updated_at    timestamptz default now()
);

create table store_channels (
  id            bigint generated always as identity primary key,
  store_id      bigint not null references stores(id) on delete cascade,
  platform      text not null check (platform in ('naver','google','csv')),
  external_url  text,
  is_competitor boolean default false,
  competitor_of bigint references stores(id),
  created_at    timestamptz default now()
);
create index idx_channels_store on store_channels(store_id);

-- ---------- 리뷰 ----------
create table reviews (
  id            bigint generated always as identity primary key,
  channel_id    bigint not null references store_channels(id) on delete cascade,
  dedup_key     text not null,                 -- hash(작성자표시명+방문일+본문 앞 50자)
  author_masked text,                          -- '김**' — 원문 표시명은 저장하지 않는다
  rating        smallint,                      -- 1~5, 네이버 미제공 시 null
  body          text not null,
  written_at    date,
  collected_at  timestamptz default now(),
  unique (channel_id, dedup_key)
);
create index idx_reviews_channel_written on reviews(channel_id, written_at desc);

create table review_analysis (
  review_id     bigint primary key references reviews(id) on delete cascade,
  sentiment     text check (sentiment in ('pos','neu','neg')),
  severity      text check (severity in ('normal','uncomfortable','complaint','malicious')),
  urgent        boolean default false,
  aspects       jsonb not null default '[]',   -- [{"category":"대기시간","polarity":"neg"}]
  keywords      text[] default '{}',
  model_ver     text,                          -- 'haiku-v1' | 'koelectra-v1' | 'failed'
  analyzed_at   timestamptz default now()
);
create index idx_analysis_urgent on review_analysis(urgent) where urgent;

create table review_embeddings (
  review_id     bigint primary key references reviews(id) on delete cascade,
  embedding     vector(1024)                   -- BGE-M3
);
create index idx_embeddings_hnsw on review_embeddings
  using hnsw (embedding vector_cosine_ops);

-- ---------- 답글 ----------
create table replies (
  id            bigint generated always as identity primary key,
  review_id     bigint not null references reviews(id) on delete cascade,
  tone          text check (tone in ('polite','friendly','apologetic')),
  draft         text not null,
  status        text default 'draft' check (status in ('draft','approved','discarded')),
  created_at    timestamptz default now(),
  approved_at   timestamptz
);
create index idx_replies_review on replies(review_id, status);

-- ---------- 집계·리포트 (읽기 경로의 심장) ----------
create table weekly_aspect_stats (
  store_id      bigint not null references stores(id) on delete cascade,
  week_start    date not null,                 -- 해당 주 월요일
  aspect        text not null,                 -- 맛/친절/청결/대기시간/가격/분위기/전체
  pos_cnt       int default 0,
  neg_cnt       int default 0,
  total_cnt     int default 0,
  avg_rating    numeric(3,2),
  primary key (store_id, week_start, aspect)
);

create table reports (
  id            bigint generated always as identity primary key,
  store_id      bigint not null references stores(id) on delete cascade,
  week_start    date not null,
  diagnosis     jsonb not null,                -- [{level,title,evidence,metric}]
  prescriptions jsonb not null,                -- [{title,detail,expected_effect}]
  created_at    timestamptz default now(),
  unique (store_id, week_start)
);

-- ---------- 알림·대화 ----------
create table alerts (
  id            bigint generated always as identity primary key,
  store_id      bigint references stores(id) on delete cascade,
  review_id     bigint references reviews(id) on delete set null,
  kind          text check (kind in ('urgent_review','digest','weekly_report','system')),
  sent_via      text[] default '{}',           -- {'kakao','webpush'}
  created_at    timestamptz default now()
);

create table chat_messages (
  id            bigint generated always as identity primary key,
  store_id      bigint references stores(id) on delete cascade,
  role          text check (role in ('user','assistant')),
  content       text not null,
  created_at    timestamptz default now()
);
create index idx_chat_store on chat_messages(store_id, created_at);

-- =============================================================================
-- ARCHITECTURE.md §3-7: 스펙 DDL에 없던 추가 테이블
-- =============================================================================

-- api → worker 수동 크롤 트리거 채널 (worker가 10초 주기 폴링)
create table crawl_jobs (
  id            bigint generated always as identity primary key,
  channel_id    bigint not null references store_channels(id) on delete cascade,
  status        text default 'pending' check (status in ('pending','running','done','failed')),
  requested_by  uuid,                          -- 트리거한 사용자 (내부 트리거는 null)
  error         text,
  created_at    timestamptz default now(),
  started_at    timestamptz,
  finished_at   timestamptz
);
create index idx_crawl_jobs_pending on crawl_jobs(status) where status = 'pending';

-- 카카오 "나에게 보내기" 발송용 토큰 (사용자별. refresh_token으로 서버가 갱신)
create table kakao_tokens (
  user_id        uuid primary key,             -- auth.users(id)
  access_token   text not null,
  refresh_token  text not null,
  expires_at     timestamptz not null,
  updated_at     timestamptz default now()
);

-- 웹푸시(VAPID) 구독. 사용자당 기기 여러 개 가능
create table push_subscriptions (
  id            bigint generated always as identity primary key,
  user_id       uuid not null,
  endpoint      text not null unique,
  p256dh        text not null,
  auth          text not null,
  created_at    timestamptz default now()
);
create index idx_push_user on push_subscriptions(user_id);

-- =============================================================================
-- RLS: 프론트가 PostgREST로 직접 접근하는 것을 차단 (백엔드는 service_role이라 무관)
-- 정책을 하나도 만들지 않으면 anon/authenticated 는 전부 거부됨
-- =============================================================================
alter table stores               enable row level security;
alter table store_settings       enable row level security;
alter table store_channels       enable row level security;
alter table reviews              enable row level security;
alter table review_analysis      enable row level security;
alter table review_embeddings    enable row level security;
alter table replies              enable row level security;
alter table weekly_aspect_stats  enable row level security;
alter table reports              enable row level security;
alter table alerts               enable row level security;
alter table chat_messages        enable row level security;
alter table crawl_jobs           enable row level security;
alter table kakao_tokens         enable row level security;
alter table push_subscriptions   enable row level security;
