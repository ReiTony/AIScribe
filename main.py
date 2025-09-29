from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from db.connection import Base, engine
from utils.logging import configure_logging, logger
from routers import auth
from routers import ai  # noqa: F401  (ensures router file is discovered)

settings = get_settings()

app = FastAPI(
	title=settings.app_name,
	docs_url=settings.docs_url,
	redoc_url=settings.redoc_url,
)

app.add_middleware(
	CORSMiddleware,
	allow_origins=settings.cors_allow_origins,
	allow_credentials=settings.cors_allow_credentials,
	allow_methods=settings.cors_allow_methods,
	allow_headers=settings.cors_allow_headers,
)


@app.on_event("startup")
def on_startup() -> None:
	configure_logging()
	logger.info("Starting application; ensuring database schema is present (development mode).")
	Base.metadata.create_all(bind=engine)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
	return {"status": "ok"}


app.include_router(auth.router)
app.include_router(ai.router)
