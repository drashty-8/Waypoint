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

**photos.beacon_id is a nullable bigint FK to beacons.id with ON
UPDATE CASCADE / ON DELETE RESTRICT.** Replaced photos.beacon_uuid once
a beacon became identified by its full UUID + Major + Minor triple (see
below): a UUID alone no longer names one beacon, so photos point at the
beacons row's id instead. Nullable because a photo can save with no
beacon match ("Location unknown" — layered fallback: auto-detect, then
manual pick from registered rooms, then skip to null). Restrict on
delete so a beacon can't be removed while photos still reference it.

**Beacons are identified by iBeacon UUID + Major + Minor, with user_id
in the unique key.** The unique key is (user_id, beacon_uuid, major,
minor). Users set up their own beacons, so they can share one UUID
across rooms and vary Minor, or use different UUIDs with the same
Major/Minor — the full triple is what tells beacons apart. user_id is
in the key so different users can reuse the same triple without
colliding. Major and Minor are integers with a CHECK of 0 to 65535,
matching iBeacon's 16-bit fields. POST /photos requires all three
together and looks up the beacon on user_id plus the triple.

**iBeacon was chosen over Eddystone-UID.** Google's Nearby Messages
API, Google's main Android-side support for Eddystone, is deprecated.
Eddystone packets can still be scanned directly with standard BLE APIs.
The beacons already broadcast iBeacon, iBeacon is assumed to be the
most likely default on beacons users configure themselves (not
verified), and Core
Location supports it natively on iOS.

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

**A blank beacon_uuid, beacon_major or beacon_minor is treated as "not
sent", not as an invalid value.** Form clients can send an empty field
instead of omitting it. An empty value carries no beacon information,
so it's handled the same as a missing one. If all three are blank or
missing, the photo saves with a null beacon_id ("Location unknown");
if only some are, that's a partial triple and returns 400.

**A failed beacon lookup in Phase 2 returns 500.** The spec only
covers the not-found case (404). A database error during the lookup is
a server-side failure, not a problem with the request, so it returns
500 and logs the error.

**The 10MB image limit is 10 * 1024 * 1024 bytes.** Checked against
how Supabase interprets the bucket's 10MB file limit (1024-based) and
it matches, so the Phase 1 check and the bucket reject at the same size.

**Tagging accuracy, as of SCRUM-34:** small/portable objects (a lip
balm, an object on a mousepad) were missed even with no prompt
constraints at all — pointing to Claude's internal image resize (~1.15
megapixels) as a likely cause, not prompt wording. A tighter crop of
just the relevant area partially confirmed this. Separately, confident
mislabeling persists despite explicit hedging instructions: a
humidifier was called an "air purifier," a router a "Google Home
speaker," a stack of books guessed as "programming or technical
manuals." Both issues are known, unresolved, and out of scope for
COMP490's three example queries (charger, whiteboard, room) — revisit
only if a real query fails because of either.

**Claude's image size limit is 10MB, measured on the base64 data, not
5MB.** The direct Claude API allows 10MB per image after base64
encoding (about a third bigger than the file); the often-quoted 5MB is
the Bedrock/Vertex limit. tagging.py checks the base64 length after any
HEIC conversion and fails with a specific log reason instead of sending
the image and getting a generic API rejection. Consequence: files of
roughly 7.5–10MB pass the bucket's 10MB upload limit but are marked
failed at tagging. Not resized — revisit if real uploads hit it. The
docs just say "10MB"; treated as 1024-based, like the bucket limit.

**Tagging forces a tool call instead of accepting free text.**
tool_choice requires record_photo_tags, with a strict schema
(description string, tags array), so every successful response has the
same shape and saving it means reading two fields, with no free-text
parsing. A response without that tool call (refusal, cut off at
max_tokens, plain text) counts as a failure. Works on Haiku 4.5, but
newer models (Opus 5.5, Fable 5.1) reject a forced tool_choice, so a
future model switch means tool_choice "auto" plus the strict tool, or
structured outputs.

**HEIC/HEIF is converted to JPEG before sending to Claude; Storage
keeps the original.** Claude only accepts JPEG, PNG, GIF and WebP. The
conversion happens in memory at tagging time (pillow-heif, same pixel
dimensions, JPEG quality 90); the stored file and image_url stay the
untouched HEIC, so nothing is lost and the conversion can change later
without re-uploading. Cost: the conversion reruns on every tagging
attempt, including SCRUM-29 retries — small next to the Claude call.

**Every trigger_tagging failure sets tagging_status = 'failed'; retry
logic is SCRUM-29.** Missing or deleted row, lookup error, download
error, unrecognized type, failed HEIC conversion, oversized image,
Claude error or no tool call, and failed save all take the same path,
so a broken photo is distinguishable from one still pending. For a
deleted row the update matches nothing — a harmless no-op. If the
database itself is down, marking failed likely fails too and the photo
stays pending, so SCRUM-29 should treat a long-stale 'pending' as
possibly failed. Telling retryable failures (rate limit, 5xx, network)
from permanent ones is left to SCRUM-29; the logged exception type is
enough to do it.

**POST /query forces a tool call on claude-haiku-4-5-20251001, the
same model as tagging.** Newer models (Opus 5.5, Sonnet 5.5) reject a
forced tool_choice with a 400. Switching to one later means
tool_choice "auto" plus a prompt instruction, with a missing tool call
treated as 502 — the code already handles that case. Check whether a
future Haiku version has the same restriction before upgrading
casually.

**Schema-valid but semantically wrong match responses return 502, not
the broken result.** The strict schema guarantees shape (integer or
null, string or null), not correctness: Claude could still name a
photo id that isn't in the candidate list, or pick a photo with a null
answer. Both are treated as a failed call rather than surfaced to the
client — the same hedge-over-guess principle as the rest of the
project.

**Live-tested: semantic matching can compensate for a wrong tagging
label, but isn't reliable for it.** "Where is my humidifier" matched
a photo whose description says "air purifier" — Claude bridged the
synonym at query time. Real evidence for free-text matching over
literal keyword/tag search, but one favorable case, not proof the
mislabeling gap (see the SCRUM-34 tagging accuracy entry above) stopped
mattering. A harder question, or a less semantically close mislabel,
would likely still surface as a missed match. Revisit together with
tagging accuracy; not resolved by this result.

**Backend hosting: Fly.io, app waypoint-backend, region lax,
shared-cpu-1x / 512MB, scale-to-zero.** min_machines_running = 0
(~1.5s cold start) rather than always-on — near-zero cost for current
usage; switch to always-on, or manually ping the server, before a live
demo to remove the cold start when it matters. Chosen over Render
(free, but ~60s cold start on the free tier) and Railway (no longer has
a true free tier). Fly's GitHub-generated Dockerfile ran the fastapi CLI
(fastapi run), which needs the fastapi[standard] extras; this project
installs plain fastapi + uvicorn, so CMD calls uvicorn directly,
matching local development. .dockerignore lists .env and venv/ —
Docker doesn't read .gitignore, so without them secrets would be baked
into the image. Secrets are set with fly secrets set; .env never ships
in the image.