-- =============================================================================
-- [로컬 개발 전용 — Supabase 에는 절대 적용하지 말 것]
-- docker postgres 에는 auth 스키마가 없다. Supabase 에서는 auth.users 가 이미 존재하므로
-- 이 파일은 로컬 개발 DB(docker-compose.dev.yml)에만 001 보다 먼저 적용한다.
-- =============================================================================

create schema if not exists auth;
create table if not exists auth.users (
  id uuid primary key default gen_random_uuid()
);
