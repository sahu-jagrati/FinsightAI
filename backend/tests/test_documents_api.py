"""Document API tests against an in-memory SQLite DB (see conftest.py).

The Redis-backed job enqueue is monkeypatched — these tests exercise the
upload/list/get/delete HTTP surface and DB persistence, not the queue
itself (that's `test_job_queue.py`, which needs a real Redis).
"""

import io

import pytest

import app.api.routes.documents as documents_route


@pytest.fixture(autouse=True)
def _stub_job_queue(monkeypatch):
    calls: list = []

    async def _fake_enqueue(document_id):
        calls.append(document_id)

    monkeypatch.setattr(documents_route, "enqueue_ingestion_job", _fake_enqueue)
    return calls


@pytest.mark.asyncio
async def test_upload_document_creates_record_and_enqueues_job(client_db, _stub_job_queue, tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    files = {"file": ("apple_10k.txt", io.BytesIO(b"Apple revenue was $394 billion."), "text/plain")}
    data = {
        "company_name": "Apple",
        "document_type": "annual_report",
        "reporting_period": "2022",
        "source": "user upload",
    }

    resp = await client_db.post("/api/documents/upload", files=files, data=data)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["original_filename"] == "apple_10k.txt"
    assert body["document_type"] == "annual_report"
    assert body["status"] == "uploaded"
    assert body["company"]["name"] == "Apple"
    assert len(_stub_job_queue) == 1


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_extension(client_db, tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    files = {"file": ("malware.exe", io.BytesIO(b"MZ..."), "application/octet-stream")}
    resp = await client_db.post("/api/documents/upload", files=files, data={})

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unsupported_file_type"


@pytest.mark.asyncio
async def test_list_get_delete_document(client_db, tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    files = {"file": ("msft_10q.txt", io.BytesIO(b"Microsoft cloud revenue grew."), "text/plain")}
    upload_resp = await client_db.post(
        "/api/documents/upload",
        files=files,
        data={"company_name": "Microsoft", "document_type": "quarterly_report"},
    )
    document_id = upload_resp.json()["id"]

    list_resp = await client_db.get("/api/documents")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1

    get_resp = await client_db.get(f"/api/documents/{document_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == document_id

    delete_resp = await client_db.delete(f"/api/documents/{document_id}")
    assert delete_resp.status_code == 204

    missing_resp = await client_db.get(f"/api/documents/{document_id}")
    assert missing_resp.status_code == 404
    assert missing_resp.json()["error"]["code"] == "not_found"
