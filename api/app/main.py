from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.config import settings
from app.routers.classes import router as classes_router
from app.routers.users import router as users_router

app = FastAPI(title="Content Extractor API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(classes_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
