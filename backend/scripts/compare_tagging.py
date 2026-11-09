"""Compare tagging output across models (and optionally a different prompt).

For each photo id and each model, this sends the stored photo to Claude
with the backend's tagging tool and prints the description and tags.

Read-only: it reads the photos row and downloads the image, but never
writes to the database or Storage and never changes tagging_status.

Every photo x model pair is ONE real, billed request. pytest never
collects this file: it only looks in tests/, and this isn't test_*.py.

Usage (from backend/, using the backend venv):
    venv/bin/python scripts/compare_tagging.py --photo-id 26 [--photo-id N ...]
        --model <model id> [--model <model id> ...]
        [--prompt-file path/to/prompt.txt]
        [--tool-choice forced|auto]

--tool-choice forced (the default) is what the backend does. Newer models
such as Opus 5.5 and Sonnet 5.5 reject a forced tool call with a 400, so
use --tool-choice auto for those. It applies to every model in the run.
"""

import argparse
import asyncio
import base64
import sys
import time
from pathlib import Path

import anthropic
import httpx
from dotenv import load_dotenv


# This file lives in backend/scripts/, so backend/ is one folder up.
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BACKEND_DIR / ".env"

# Make the backend importable so we can reuse its code instead of copying
# it. load_dotenv runs first because importing the backend also imports
# database.py and claude_client.py, which need the settings from .env.
load_dotenv(ENV_PATH)
sys.path.insert(0, str(BACKEND_DIR))
from routers.photos import detect_image_type  # noqa: E402
from tagging import (  # noqa: E402
    MAX_CLAUDE_IMAGE_BASE64_BYTES,
    TAGGING_PROMPT,
    download_image,
    fetch_photo_row,
    find_tag_result,
    prepare_image_for_claude,
    request_tags,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Compare tagging output across models.")
    parser.add_argument(
        "--photo-id", type=int, action="append", required=True,
        help="Photo id to tag. Repeat for several photos.",
    )
    parser.add_argument(
        "--model", action="append", required=True,
        help="Claude model id. Repeat for several models.",
    )
    parser.add_argument(
        "--prompt-file", type=Path,
        help="Text file to use as the prompt instead of the backend's TAGGING_PROMPT.",
    )
    parser.add_argument(
        "--tool-choice", choices=["forced", "auto"], default="forced",
        help="forced (default) requires the tool call, like the backend; auto lets the model choose.",
    )
    parser.add_argument(
        "--repeat", type=int, default=1,
        help="Run each photo and model this many times (default 1). Each run is a billed request.",
    )
    args = parser.parse_args()

    if args.repeat < 1:
        parser.error("--repeat must be at least 1")

    return args


def tool_choice_for(mode: str) -> dict | None:
    """Return the tool_choice to pass to request_tags for this mode."""
    if mode == "auto":
        return {"type": "auto"}

    # None makes request_tags use its default: the forced tool call.
    return None


def load_photo_for_claude(photo_id: int) -> tuple[str, str] | None:
    """Fetch, download and prepare the photo the same way trigger_tagging does.

    Returns (image_base64, media_type), or None after printing why the
    photo can't be sent. Unlike trigger_tagging, a failure here changes
    nothing in the database.
    """
    try:
        photo = fetch_photo_row(photo_id)
    except Exception as error:
        print(f"Photo {photo_id}: could not fetch the row: {error}")
        return None

    if photo is None:
        print(f"Photo {photo_id}: no such row.")
        return None

    try:
        image_bytes = asyncio.run(download_image(photo["image_url"]))
    except httpx.HTTPError as error:
        print(f"Photo {photo_id}: could not download the image: {error}")
        return None

    image_type = detect_image_type(image_bytes)
    if image_type is None:
        print(f"Photo {photo_id}: unrecognized image type.")
        return None

    try:
        send_bytes, media_type = prepare_image_for_claude(image_bytes, image_type)
    except Exception as error:
        print(f"Photo {photo_id}: could not convert the {image_type} image: {error}")
        return None

    image_base64 = base64.standard_b64encode(send_bytes).decode("utf-8")
    if len(image_base64) > MAX_CLAUDE_IMAGE_BASE64_BYTES:
        print(f"Photo {photo_id}: image exceeds Claude's 10MB limit (base64-encoded); not sending it.")
        return None

    return image_base64, media_type


def print_result(response, mode: str) -> None:
    """Print the description and tags, or whatever Claude sent instead."""
    tag_result = find_tag_result(response)
    if tag_result is not None:
        print(f"description: {tag_result['description']}")
        print(f"tags: {', '.join(tag_result['tags'])}")
        return

    # No complete tool call. Under auto, the model may have answered in text.
    text_parts = [block.text for block in response.content if block.type == "text"]
    if mode == "auto" and len(text_parts) > 0:
        print(f"No tool call; the model replied with text (stop_reason={response.stop_reason}):")
        print("\n".join(text_parts))
        return

    print(f"No tool call in the response (stop_reason={response.stop_reason}).")


def main():
    args = parse_args()

    if args.prompt_file is not None:
        prompt = args.prompt_file.read_text()
        prompt_label = str(args.prompt_file)
    else:
        prompt = TAGGING_PROMPT
        prompt_label = "TAGGING_PROMPT (backend default)"

    tool_choice = tool_choice_for(args.tool_choice)

    for photo_id in args.photo_id:
        # Fetched once per photo, then reused for every model, so every
        # model sees exactly the same image bytes.
        prepared = load_photo_for_claude(photo_id)
        if prepared is None:
            continue
        image_base64, media_type = prepared

        for model in args.model:
            for run in range(1, args.repeat + 1):
                print(
                    f"\n=== photo {photo_id} | model {model} | tool_choice {args.tool_choice} "
                    f"| run {run} of {args.repeat} ==="
                )
                print(f"prompt: {prompt_label}")

                # perf_counter is meant for measuring durations; the SDK's own
                # retries happen inside request_tags, so they count toward this time.
                start = time.perf_counter()
                try:
                    response = request_tags(
                        image_base64, media_type, model=model, prompt=prompt, tool_choice=tool_choice
                    )
                except anthropic.APIError as error:
                    elapsed = time.perf_counter() - start
                    print(f"API error after {elapsed:.1f}s: {error}")
                    continue
                elapsed = time.perf_counter() - start

                print_result(response, args.tool_choice)
                print(
                    f"usage: {response.usage.input_tokens} input tokens, "
                    f"{response.usage.output_tokens} output tokens"
                )
                print(f"elapsed: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
