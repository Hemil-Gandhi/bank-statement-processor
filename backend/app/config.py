"""Application configuration.

All settings are environment-overridable so the same code runs locally and in Docker.
Money is handled with Decimal throughout the domain layer.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Settings:
    app_name: str = "Bank Statement Processing & Classification System"
    version: str = "1.0.0"

    backend_dir: Path = Path(__file__).resolve().parent.parent
    project_root: Path = backend_dir.parent

    data_dir: Path = Path(os.getenv("BSP_DATA_DIR", str(backend_dir / "data")))
    upload_dir: Path = Path(os.getenv("BSP_UPLOAD_DIR", str(data_dir / "uploads")))
    model_path: Path = Path(
        os.getenv("BSP_MODEL_PATH", str(data_dir / "models" / "classifier.joblib"))
    )
    training_csv: Path = Path(
        os.getenv("BSP_TRAINING_CSV", str(data_dir / "training" / "transactions_labeled.csv"))
    )
    docs_dir: Path = Path(os.getenv("BSP_DOCS_DIR", str(project_root / "docs")))
    samples_dir: Path = Path(os.getenv("BSP_SAMPLES_DIR", str(project_root / "samples")))
    frontend_dir: Path = Path(
        os.getenv("BSP_FRONTEND_DIR", str(project_root / "frontend"))
    )

    database_url: str = os.getenv(
        "BSP_DATABASE_URL", f"sqlite:///{(data_dir / 'app.db').as_posix()}"
    )

    max_file_size: int = _env_int("BSP_MAX_FILE_SIZE_MB", 25) * 1024 * 1024
    max_pages: int = _env_int("BSP_MAX_PAGES", 100)

    ocr_dpi: int = _env_int("BSP_OCR_DPI", 300)
    ocr_min_confidence: int = _env_int("BSP_OCR_MIN_CONF", 30)
    ocr_psm: int = _env_int("BSP_OCR_PSM", 6)
    ocr_language: str = os.getenv("BSP_OCR_LANG", "eng")

    # Uploaded files are deleted immediately after processing (privacy by design).
    delete_uploads_after_processing: bool = os.getenv(
        "BSP_KEEP_UPLOADS", "0"
    ).lower() not in {"1", "true", "yes"}

    log_level: str = os.getenv("BSP_LOG_LEVEL", "INFO")

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.upload_dir,
            self.model_path.parent,
            self.training_csv.parent,
            self.docs_dir,
            self.samples_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def tesseract_cmd(self) -> str | None:
        env = os.getenv("TESSERACT_CMD")
        if env and Path(env).exists():
            return env
        found = shutil.which("tesseract")
        if found:
            return found
        candidates = [
            Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
            Path(os.getenv("LOCALAPPDATA", "")) / "Tesseract-OCR" / "tesseract.exe",
            Path("/usr/bin/tesseract"),
            Path("/usr/local/bin/tesseract"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None


settings = Settings()
settings.ensure_dirs()
