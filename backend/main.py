import logging

from fastapi import FastAPI

from routers import photos


logging.basicConfig(level=logging.INFO)

app = FastAPI()

# Each group of endpoints lives in its own file under routers/.
app.include_router(photos.router)

@app.get("/")
def root():
    return {"status": "ok"}
