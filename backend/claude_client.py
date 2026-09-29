import os

from anthropic import Anthropic
from dotenv import load_dotenv


load_dotenv()

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# One shared Claude client, imported by anything that needs to call Claude.
client = Anthropic(api_key=ANTHROPIC_API_KEY)
