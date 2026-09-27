# Decisions log

Compressed reasoning behind non-obvious calls — not a full transcript,
enough to evaluate whether a decision still holds if circumstances change.

**RLS disabled on all tables.** COMP490 has no real users or auth yet.
Supabase's security-advisor emails flagging this are expected. Revisit
when COMP491 adds real Supabase Auth.

**Photos upload through a FastAPI endpoint, not straight from mobile
to Supabase.** Considered mobile writing directly via the Supabase
client SDK; rejected because detecting "a photo just got uploaded" on
the backend then needs a webhook, a Realtime subscription, or polling
— infrastructure this project doesn't have. Routing uploads through
one endpoint means the same code that inserts the row calls tagging
on its next line, no detection step needed.

**beacon_uuid is nullable, uuid type, FK to beacons with ON UPDATE
CASCADE / ON DELETE RESTRICT.** Nullable because a photo can save with
no beacon match ("Location unknown" — layered fallback: auto-detect,
then manual pick from registered rooms, then skip to null). Type
matches iBeacon UUIDs, already UUID-formatted. Cascade on update so a
corrected beacon UUID propagates; restrict on delete so a beacon can't
be removed while photos still reference it.

**captured_at is separate from created_at.** captured_at is when the
photo was taken (client-supplied); created_at is when the row was
written. Kept distinct for a possible future camera-roll-upload
feature, where the two could differ significantly.

**Stored photo resolution is not yet pinned to Claude's own internal
resize limit (~1568px long edge), though there's a real argument for
doing so** — it would remove any coordinate-scaling step for a future
bounding-box UI, since Claude wouldn't need to resize a file that's
already at its target size. Tested against a real whiteboard-text
photo and confirmed legible at that resolution, so pinning to it
wouldn't sacrifice the whiteboard-reading use case. Not yet implemented
in SCRUM-22 — a COMP491 task tied to the box-review UI, not blocking
anything this semester.

**raw_ai_response column was considered and dropped from the photos
migration.** Would only hold new information if the Claude prompt also
requested per-object bounding boxes — not planned this semester. Without
that, it would just duplicate description/tags as JSON. Revisit
together with the objects-array prompt change when COMP491 builds the
box-review UI.

**tags is a separate text[] column, not folded into description.**
description stays a full sentence for a human reading a query result;
tags is a short list of discrete object names from the same Claude
call, enabling cheaper filtering/matching later and unblocking
SCRUM-48 (advanced filter/sort), whether or not that story ships
this semester.