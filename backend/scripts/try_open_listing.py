"""Diagnostic: does Claude notice small objects when nothing constrains the output?

No tool, no schema, no length guidance in the prompt. Makes ONE real, billed
request with the same model and image handling as try_claude_tagging.py.

Usage:
    venv/bin/python scripts/try_open_listing.py /path/to/photo.jpg  (from backend/)
"""

import base64
import sys
from pathlib import Path

import anthropic

# Reuses the model, .env loading and HEIC handling from the tagging script.
from try_claude_tagging import MAX_CLAUDE_IMAGE_BASE64_BYTES, MODEL, prepare_image


PROMPT = "List every distinct object visible in this photo, however small, with no limit on how many."

# max_tokens is required by the API, so set it well above any plausible
# list length. stop_reason is printed so a cut-off answer would be obvious.
MAX_TOKENS = 8192


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python try_open_listing.py /path/to/photo.jpg")
    image_path = Path(sys.argv[1])

    image_bytes, media_type = prepare_image(image_path.read_bytes())
    image_base64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    if len(image_base64) > MAX_CLAUDE_IMAGE_BASE64_BYTES:
        sys.exit("Image exceeds Claude's 10MB limit (base64-encoded); not sending it.")

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": image_base64},
                },
                {"type": "text", "text": PROMPT},
            ],
        }],
    )

    print("=== Raw response ===")
    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
