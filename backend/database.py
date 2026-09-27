import os

from dotenv import load_dotenv
from supabase import create_client


load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

# One shared Supabase client, imported by every router that needs it.
supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
