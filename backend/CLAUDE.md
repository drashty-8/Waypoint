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
- beacon_uuid uuid, nullable, FK -> beacons.beacon_uuid,
  ON UPDATE CASCADE / ON DELETE RESTRICT
- tagging_status text, NOT NULL, default 'pending',
  CHECK IN ('pending', 'complete', 'failed')

### beacons
- id int8, PK
- beacon_uuid uuid, UNIQUE, NOT NULL
- room_name text, NOT NULL
- user_id uuid, NOT NULL, shared placeholder value
- created_at timestamptz, default now()

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

## Code style
- Prefer readable, explainable code over clever one-liners — e.g.
  if/else over ternary chains, URLSearchParams over manually building
  a URL with new URL().
- Explain changes at a level someone newer to the codebase could follow.
- Don't make changes beyond what was asked without flagging them first.