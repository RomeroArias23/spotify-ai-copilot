from fastapi import FastAPI

from app.api.routes.auth import router as auth_router
from app.api.routes.me import router as me_router

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

app = FastAPI(title="Spotify AI Copilot")

app.include_router(auth_router)
app.include_router(me_router)


@app.get("/")
def root():
    return {"message": "Spotify AI Copilot is running"}
