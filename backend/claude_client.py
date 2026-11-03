import os

from anthropic import Anthropic
from dotenv import load_dotenv


load_dotenv()

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# One shared Claude client, imported by anything that needs to call Claude.
# 30s instead of the SDK's 10-minute default so a hung call fails fast;
# 2 retries (the default, made explicit) cover timeouts, network errors, 429 and 5xx.
client = Anthropic(api_key=ANTHROPIC_API_KEY, timeout=30.0, max_retries=2)
