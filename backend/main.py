import os

from dotenv import load_dotenv
from fastapi import FastAPI


load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok"}