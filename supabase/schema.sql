create table if not exists public.telegram_subscribers (
  chat_id text primary key,
  username text,
  first_name text,
  last_name text,
  chat_type text,
  is_active boolean not null default true,
  subscribed_at timestamptz,
  unsubscribed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists telegram_subscribers_active_idx
  on public.telegram_subscribers (is_active);
