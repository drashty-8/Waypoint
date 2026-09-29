"""One-off check of the SCRUM-34 tagging call against the real Claude API.

Makes ONE real, billed request. pytest never collects it: it only looks in
tests/, and this file isn't named test_*.py.

Usage (from backend/, using the backend venv):
    venv/bin/python scripts/try_claude_tagging.py /path/to/photo.jpg
"""

import base64
import io
import json
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from PIL import Image
import pillow_heif


# This file lives in backend/scripts/, so backend/ is one folder up.
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BACKEND_DIR / ".env"
MODEL = "claude-haiku-4-5-20251001"

# Claude can't read HEIC/HEIF, so those get re-encoded as JPEG first.
HEIF_TYPES = {"image/heic", "image/heif"}
JPEG_QUALITY = 90

# Lets Pillow's Image.open() read HEIC/HEIF files.
pillow_heif.register_heif_opener()

# Make the backend importable so we can reuse its code instead of copying
# it. load_dotenv runs first because importing the backend also imports
# database.py and claude_client.py, which need the settings from .env.
load_dotenv(ENV_PATH)
sys.path.insert(0, str(BACKEND_DIR))
from routers.photos import detect_image_type  # noqa: E402
# Same prompt, tool and size limit the backend uses, so this script can't drift from it.
from tagging import MAX_CLAUDE_IMAGE_BASE64_BYTES, TAGGING_PROMPT, TAGGING_TOOL  # noqa: E402



def prepare_image(image_bytes: bytes) -> tuple[bytes, str]:
    """Return image bytes Claude can read, plus their MIME type.

    HEIC/HEIF is decoded and re-encoded as JPEG at the same pixel
    dimensions. Any other type is sent unchanged.
    """
    image_type = detect_image_type(image_bytes)
    if image_type is None:
        sys.exit("Could not recognize the image type.")

    if image_type not in HEIF_TYPES:
        return image_bytes, image_type

    image = Image.open(io.BytesIO(image_bytes))
    # JPEG has no alpha channel or 10-bit color, so convert to plain 8-bit RGB.
    rgb_image = image.convert("RGB")

    output = io.BytesIO()
    rgb_image.save(output, format="JPEG", quality=JPEG_QUALITY)
    jpeg_bytes = output.getvalue()

    print(
        f"Converted {image_type} to JPEG: {image.width}x{image.height}, "
        f"{len(image_bytes):,} -> {len(jpeg_bytes):,} bytes"
    )
    return jpeg_bytes, "image/jpeg"


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python try_claude_tagging.py /path/to/photo.jpg")
    image_path = Path(sys.argv[1])

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(f"ANTHROPIC_API_KEY is not set in {ENV_PATH}")

    original_bytes = image_path.read_bytes()
    print(f"Image: {image_path} ({len(original_bytes):,} bytes)")

    image_bytes, media_type = prepare_image(original_bytes)
    image_base64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    if len(image_base64) > MAX_CLAUDE_IMAGE_BASE64_BYTES:
        sys.exit("Image exceeds Claude's 10MB limit (base64-encoded); not sending it.")

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        tools=[TAGGING_TOOL],
        # Force Claude to answer by calling the tool, not with plain text.
        tool_choice={"type": "tool", "name": "record_photo_tags"},
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": image_base64},
                },
                {"type": "text", "text": TAGGING_PROMPT},
            ],
        }],
    )

    print("\n=== Full response ===")
    print(response.model_dump_json(indent=2))

    print("\n=== Tool call result ===")
    print(f"stop_reason: {response.stop_reason}")
    tool_calls = [block for block in response.content if block.type == "tool_use"]
    if len(tool_calls) == 0:
        print("No tool call in the response.")
    else:
        print(json.dumps(tool_calls[0].input, indent=2))

    print("\n=== Usage ===")
    print(f"input tokens: {response.usage.input_tokens}, output tokens: {response.usage.output_tokens}")


if __name__ == "__main__":
    main()
