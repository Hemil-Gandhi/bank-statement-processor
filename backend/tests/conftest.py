"""Shared pytest fixtures and import-path setup."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

SAMPLES = PROJECT / "samples"


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    if not SAMPLES.exists():
        pytest.skip("sample PDFs are missing; run scripts/generate_sample_pdfs.py")
    return SAMPLES


@pytest.fixture(scope="session")
def sbi_pdf(samples_dir: Path) -> Path:
    return samples_dir / "sbi_statement.pdf"


@pytest.fixture(scope="session")
def generic_pdf(samples_dir: Path) -> Path:
    return samples_dir / "generic_statement.pdf"
