from fastapi import FastAPI
from app.api.routes.auth import router as auth_router

app = FastAPI(title="Spotify AI Copilot")

app.include_router(auth_router)


@app.get("/")
def root():
    return {"message": "Spotify AI Copilot is running"}
