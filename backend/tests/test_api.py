"""API integration tests: upload, history, results, editing, exports and errors."""
from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import app
from app.models.db_models import Base


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )

    def override_get_db():
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _upload(client: TestClient, path: Path, password: str | None = None):
    files = {"file": (path.name, path.read_bytes(), "application/pdf")}
    data = {"password": password} if password else None
    return client.post("/api/statements", files=files, data=data)


def test_health_info_categories_and_rules(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["database"] == "ok"

    info = client.get("/api/info")
    assert info.status_code == 200
    assert "no external ai" in info.json()["privacy"].lower()

    categories = client.get("/api/categories")
    assert categories.status_code == 200
    names = {item["name"] for item in categories.json()}
    assert "Salary/Income" in names and "Uncategorized" in names

    rules = client.get("/api/rules")
    assert rules.status_code == 200
    assert any(rule["id"] == "salary_credit" for rule in rules.json())


def test_upload_results_summary_edit_and_export(client: TestClient, sbi_pdf: Path) -> None:
    response = _upload(client, sbi_pdf)
    assert response.status_code == 201, response.text
    statement = response.json()
    statement_id = statement["id"]
    assert statement["bank_detected"] == "State Bank of India"
    assert statement["pdf_type"] == "TEXT"
    assert statement["stats"]["transaction_count"] == 36
    assert statement["stats"]["closing_reconciled"] is True
    assert statement["stats"]["reconciled_ratio"] == 1.0
    assert statement["account"]["account_holder_name"] == "SAMPLE CUSTOMER"

    history = client.get("/api/statements")
    assert history.status_code == 200
    assert history.json()[0]["id"] == statement_id
    assert history.json()[0]["transaction_count"] == 36

    page = client.get(
        f"/api/statements/{statement_id}/transactions",
        params={"page": 1, "page_size": 10},
    )
    assert page.status_code == 200
    payload = page.json()
    assert payload["total"] == 36
    assert len(payload["items"]) == 10
    assert payload["pages"] == 4

    debits = client.get(
        f"/api/statements/{statement_id}/transactions",
        params={"type": "debit", "page_size": 100},
    ).json()
    assert debits["total"] > 0
    assert all(item["debit"] is not None and item["credit"] is None for item in debits["items"])

    searched = client.get(
        f"/api/statements/{statement_id}/transactions",
        params={"search": "salary"},
    ).json()
    assert searched["total"] >= 1

    summary = client.get(f"/api/statements/{statement_id}/summary")
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["transaction_count"] == 36
    assert summary_body["closing_reconciled"] is True
    assert summary_body["category_breakdown"]
    assert summary_body["balance_series"]
    assert summary_body["monthly"]

    first = payload["items"][0]
    patched = client.patch(
        f"/api/transactions/{first['id']}",
        json={"category": "Donations", "apply_to_similar": False},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["transaction"]["category"] == "Donations"
    assert patched.json()["override_saved"] is True

    overrides = client.get(f"/api/statements/{statement_id}/overrides")
    assert overrides.status_code == 200
    assert any(item["category"] == "Donations" for item in overrides.json())

    invalid = client.patch(
        f"/api/transactions/{first['id']}",
        json={"category": "Not A Category", "apply_to_similar": False},
    )
    assert invalid.status_code == 422

    xlsx = client.get(f"/api/statements/{statement_id}/export", params={"format": "xlsx"})
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK"
    assert "attachment" in xlsx.headers["content-disposition"]

    csv_response = client.get(
        f"/api/statements/{statement_id}/export",
        params={"format": "csv", "type": "debit"},
    )
    assert csv_response.status_code == 200
    rows = list(csv.reader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
    assert rows[0][0] == "Date"
    assert len(rows) > 1
    assert all(row[5] == "" for row in rows[1:])

    filtered = client.get(
        f"/api/statements/{statement_id}/export",
        params={"format": "csv", "search": "no-such-description"},
    )
    assert filtered.status_code == 404
    assert filtered.json()["detail"]["code"] == "NO_TRANSACTIONS_FOUND"

    deleted = client.delete(f"/api/statements/{statement_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/statements/{statement_id}").status_code == 404


def test_merge_export_combines_two_statements(client: TestClient, sbi_pdf: Path, generic_pdf: Path) -> None:
    first = _upload(client, sbi_pdf)
    second = _upload(client, generic_pdf)
    assert first.status_code == 201 and second.status_code == 201
    ids = f"{first.json()['id']},{second.json()['id']}"

    merged = client.get("/api/merge/export", params={"ids": ids, "format": "csv"})
    assert merged.status_code == 200
    rows = list(csv.reader(io.StringIO(merged.content.decode("utf-8-sig"))))
    assert rows[0][0] == "Statement"
    assert len(rows) == 36 + 8 + 1
    assert {row[0] for row in rows[1:]} == {"sbi_statement.pdf", "generic_statement.pdf"}

    missing = client.get("/api/merge/export", params={"ids": "does-not-exist"})
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "STATEMENT_NOT_FOUND"


def test_password_protected_pdf_requires_and_accepts_password(
    client: TestClient, samples_dir: Path
) -> None:
    pdf = samples_dir / "password_protected.pdf"
    missing = _upload(client, pdf)
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "NEEDS_PASSWORD"

    wrong = _upload(client, pdf, password="wrong-password")
    assert wrong.status_code == 422
    assert wrong.json()["detail"]["code"] == "NEEDS_PASSWORD"

    unlocked = _upload(client, pdf, password="demo123")
    assert unlocked.status_code == 201, unlocked.text
    assert unlocked.json()["password_protected"] is True
    assert unlocked.json()["stats"]["transaction_count"] > 0


def test_empty_pdf_returns_no_transactions(client: TestClient, samples_dir: Path) -> None:
    response = _upload(client, samples_dir / "empty.pdf")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "NO_TRANSACTIONS_FOUND"
    assert client.get("/api/statements").json() == []


def test_invalid_uploads_are_rejected(client: TestClient, tmp_path: Path) -> None:
    not_pdf = tmp_path / "notes.txt"
    not_pdf.write_text("hello", encoding="utf-8")
    response = _upload(client, not_pdf)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_FILE"

    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 this is not really a pdf")
    response = _upload(client, broken)
    assert response.status_code == 422

    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"not a pdf at all")
    response = _upload(client, fake_pdf)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_FILE"


def test_unknown_statement_and_transaction_are_404(client: TestClient) -> None:
    assert client.get("/api/statements/missing").status_code == 404
    assert client.get("/api/statements/missing/transactions").status_code == 404
    assert client.get("/api/statements/missing/summary").status_code == 404
    assert client.patch("/api/transactions/99999", json={"category": "Rent"}).status_code == 404


def test_retrain_endpoint_returns_model_metadata(client: TestClient, monkeypatch) -> None:
    import app.api.routes_meta as routes_meta

    monkeypatch.setattr(
        routes_meta,
        "train_model",
        lambda **_kwargs: {
            "status": "ok",
            "samples": 1234,
            "model_path": "test/model.joblib",
            "accuracy": 0.95,
        },
    )
    monkeypatch.setattr(routes_meta, "reset_engine", lambda: None)

    response = client.post("/api/classify/retrain")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["samples"] == 1234
    assert body["accuracy"] == 0.95
    assert body["overrides_used"] == 0
    assert body["model_path"] == "test/model.joblib"
