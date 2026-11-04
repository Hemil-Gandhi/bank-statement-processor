"""FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import routes_export, routes_meta, routes_results, routes_upload
from app.classification.ml_model import model_available
from app.config import settings
from app.core.errors import PipelineError
from app.core.ocr_extractor import ocr_available, tesseract_version
from app.db import init_db
from app.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    logger.info(
        "starting %s v%s | OCR=%s | model=%s",
        settings.app_name,
        settings.version,
        "yes" if ocr_available() else "no",
        "yes" if model_available() else "no",
    )
    if not ocr_available():
        logger.warning(
            "Tesseract is not available: text PDFs work, scanned PDFs need tesseract-ocr."
        )
    if not model_available():
        logger.warning(
            "Classifier model missing. Rules still work; run `python -m app.classification.train`."
        )
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "Bank statement extraction, table reconstruction, balance reconciliation and "
        "non-LLM transaction classification. Rules + TF-IDF classical ML only."
    ),
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(PipelineError)
async def pipeline_error_handler(_request: Request, exc: PipelineError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": "INVALID_REQUEST",
                "message": "Request validation failed.",
                "errors": exc.errors(),
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Check the server logs.",
            }
        },
    )


app.include_router(routes_upload.router, prefix="/api")
app.include_router(routes_results.router, prefix="/api")
app.include_router(routes_export.router, prefix="/api")
app.include_router(routes_meta.router, prefix="/api")


@app.get("/api/info", tags=["meta"])
def info() -> dict:
    return {
        "app": settings.app_name,
        "version": settings.version,
        "ocr_available": ocr_available(),
        "tesseract_version": tesseract_version(),
        "model_available": model_available(),
        "max_file_size_mb": settings.max_file_size // (1024 * 1024),
        "max_pages": settings.max_pages,
        "ocr_dpi": settings.ocr_dpi,
        "privacy": "Uploaded files are deleted after processing; no external AI services are used.",
    }


if settings.samples_dir.exists():
    app.mount(
        "/samples",
        StaticFiles(directory=str(settings.samples_dir)),
        name="samples",
    )

if settings.frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(settings.frontend_dir), html=True), name="frontend")
else:  # pragma: no cover
    @app.get("/")
    def root() -> dict:
        return {"message": "API is running. Frontend directory not found.", "docs": "/api/docs"}
