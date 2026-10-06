# Waypoint

Phone-based visual recall app: capture a photo, tag its BLE-beacon room
location, an AI service describes/tags the photo, and a natural-language
query later returns the matching photo as evidence (e.g. "where did I
leave my charger?").

## Stack
- Mobile: React Native
- Backend: Python + FastAPI
- Database/Storage: Supabase (Postgres + Storage)
- Vision/tagging: Claude API (default; GPT-4o tested later, abstracted
  so both can be swapped in)

## Current schema

### photos
- id int8, PK
- user_id uuid, NOT NULL, shared placeholder value (see decisions log)
- captured_at timestamptz, NOT NULL — when the photo was taken
- created_at timestamptz, default now() — when the row was written
- description text, nullable — filled by tagging
- tags text[], nullable — filled by tagging
- image_url text, NOT NULL
- beacon_id bigint, nullable, FK -> beacons.id,
  ON UPDATE CASCADE / ON DELETE RESTRICT
- tagging_status text, NOT NULL, default 'pending',
  CHECK IN ('pending', 'complete', 'failed')

### beacons
- id int8, PK
- beacon_uuid uuid, NOT NULL
- major integer, NOT NULL, CHECK between 0 and 65535
- minor integer, NOT NULL, CHECK between 0 and 65535
- room_name text, NOT NULL
- user_id uuid, NOT NULL, shared placeholder value
- created_at timestamptz, default now()
- UNIQUE (user_id, beacon_uuid, major, minor) — a beacon is identified
  by the full triple, so several beacons can share a uuid

### Storage bucket "photos"
Public, 10MB file limit, MIME types: jpeg, png, webp, heic, heif.

## Do not touch / do not "fix"
- RLS is deliberately disabled on every table. Supabase's security
  advisor flags this automatically — expected, not a bug. Do not
  enable RLS or suggest it as a fix.
- user_id is a single hardcoded placeholder UUID across every table,
  not per-user auth. Real auth is COMP491 scope.
- Query modality is text-based end to end. Voice transcribes to text
  client-side and feeds the same text pipeline — no separate
  voice-handling path on the backend.

See docs/decisions.md for the reasoning behind these and other calls.

## Conventions
- Branch prefixes: feature/, fix/, docs/, chore/
- After merging: git checkout main && git pull && git branch -d <branch>
- Endpoints: one APIRouter per resource in backend/routers/<name>.py
  (e.g. routers/photos.py, routers/query.py), registered in main.py
  with app.include_router(...). Import the shared Supabase client from
  database.py, never from main.py (that creates a circular import).
- Tests: run pytest from backend/ before considering any endpoint
  change complete. Tests live in backend/tests/ and use the
  fake_supabase fixture from conftest.py, never a real Supabase project.

## Code style
- Prefer readable, explainable code over clever one-liners — e.g.
  if/else over ternary chains, URLSearchParams over manually building
  a URL with new URL().
- Explain changes at a level someone newer to the codebase could follow.
- Don't make changes beyond what was asked without flagging them first.