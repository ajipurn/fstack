from fastapi import APIRouter

from app.api.routes import auth, health, jobs, models, prompts, providers, runs, usage

api_router = APIRouter()
# Registration order is matching order: keep specific paths ahead of generic ones.
for module in (health, auth, providers, prompts, runs, models, usage, jobs):
    api_router.include_router(module.router)
