"""FastAPI entry point; routes and business logic live in focused packages."""

from fastapi import FastAPI

from .api.routes import router

app = FastAPI(
    title="Loan Review Checkpoint API",
    version="0.1.0",
    description="Offline sample-format backend slice using fictional policy. No credit decisions.",
)
app.include_router(router)
