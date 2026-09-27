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

**POST /photos detects the image type from the file's bytes, not the
client's Content-Type header.** The header is client-controlled, so an
.exe labelled image/jpeg would pass a header check. The bucket's own
MIME allowlist doesn't catch it either, since it trusts the
Content-Type we send on upload. The detected type now drives the
allowlist check, the Storage file extension and the Content-Type sent
to Storage. Uses the pure-Python filetype package rather than
python-magic, so there's no system libmagic install for teammates or
servers. filetype only recognizes HEIC files branded "heic", so a
small brand check covers plain HEIF ("mif1", "msf1") and HEIC variants
like "heix"; these are stored as image/heif. Only the file header is
checked, not that the whole file decodes: enough to stop a renamed
executable or script, not a deliberately crafted file with a valid
image header.

**HEIC variants caught by the brand check are labelled image/heif.**
heix, heim, heis, hevc and hevx are really HEIC variants, but they get
stored as .heif with Content-Type image/heif. Known and left as-is:
HEIC is a subset of HEIF, so the label is still accurate at the
container level, and nothing downstream depends on the distinction.

**POST /photos returns 400, not FastAPI's default 422, for missing
fields.** FastAPI rejects a missing required field with 422 before the
endpoint runs. The spec calls for 400 on every Phase 1 failure, so the
fields are Optional in the signature and the endpoint's own checks
raise the 400.

**A blank beacon_uuid is treated as "not sent", not as an invalid
UUID.** Form clients can send an empty field instead of omitting it.
An empty value carries no beacon, so it's handled the same as a
missing one (null beacon, "Location unknown") rather than rejected.

**A failed beacon lookup in Phase 2 returns 500.** The spec only
covers the not-found case (404). A database error during the lookup is
a server-side failure, not a problem with the request, so it returns
500 and logs the error.

**The 10MB image limit is 10 * 1024 * 1024 bytes.** Checked against
how Supabase interprets the bucket's 10MB file limit (1024-based) and
it matches, so the Phase 1 check and the bucket reject at the same size.