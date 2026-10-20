import io
import os
from pathlib import Path
import zipfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core import config
from app.core.database import Base, get_db
from app.main import app


def create_zip_bytes(files_dict: dict) -> bytes:
    """Helper to build in-memory zip file from dict of filename -> bytes or str."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, content in files_dict.items():
            if isinstance(content, str):
                content = content.encode("utf-8")
            zf.writestr(fname, content)
    return buf.getvalue()


@pytest.fixture
def client_env(tmp_path, monkeypatch):
    """Fixture providing TestClient with temporary DB and temporary WORKSPACE_DIR."""
    test_db_file = tmp_path / "test_upload.db"
    test_db_url = f"sqlite:///{test_db_file}"

    test_workspace = tmp_path / "workspaces"
    test_workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "WORKSPACE_DIR", test_workspace)

    test_engine = create_engine(
        test_db_url,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client, test_workspace

    app.dependency_overrides.clear()
    test_engine.dispose()


def auth_headers(client, email="dev@example.com", password="password123"):
    """Helper to register and login a user, returning Authorization headers."""
    client.post("/api/auth/register", json={"email": email, "password": password})
    login_resp = client.post("/api/auth/login", json={"email": email, "password": password})
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_valid_zip_upload(client_env):
    """Verify that a valid ZIP archive with a root Dockerfile extracts successfully."""
    client, workspace = client_env
    headers = auth_headers(client, "alice@example.com")

    # Create project
    proj_resp = client.post("/api/projects", json={"name": "Alice App"}, headers=headers)
    project_id = proj_resp.json()["id"]

    # Build valid zip
    valid_files = {
        "Dockerfile": "FROM python:3.11-slim\nCMD [\"python\", \"-m\", \"http.server\", \"8000\"]",
        "app.py": "print('hello')",
        "sub/module.py": "x = 1",
    }
    zip_bytes = create_zip_bytes(valid_files)

    response = client.post(
        f"/api/projects/{project_id}/upload",
        files={"file": ("app.zip", zip_bytes, "application/zip")},
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["project_id"] == project_id
    assert data["extracted_files"] == 3
    assert "upload_id" in data

    upload_id = data["upload_id"]
    extracted_path = workspace / f"project_{project_id}" / upload_id
    assert (extracted_path / "Dockerfile").exists()
    assert (extracted_path / "app.py").exists()
    assert (extracted_path / "sub" / "module.py").exists()
    # Confirm temp zip was removed
    assert not (workspace / f"project_{project_id}" / f"temp_{upload_id}.zip").exists()


def test_missing_dockerfile_rejected_and_cleaned_up(client_env):
    """Verify rejection when Dockerfile is missing from root, and clean directory rollback."""
    client, workspace = client_env
    headers = auth_headers(client, "no_dockerfile@example.com")

    proj_resp = client.post("/api/projects", json={"name": "No Dockerfile"}, headers=headers)
    project_id = proj_resp.json()["id"]

    files = {
        "app.py": "print('hello')",
        "sub/Dockerfile": "FROM alpine",  # Dockerfile inside subdirectory does not satisfy root Dockerfile requirement
    }
    zip_bytes = create_zip_bytes(files)

    response = client.post(
        f"/api/projects/{project_id}/upload",
        files={"file": ("app.zip", zip_bytes, "application/zip")},
        headers=headers,
    )

    assert response.status_code == 400
    assert "Dockerfile" in response.json()["detail"]

    # Ensure no extracted folders exist under the project directory
    proj_dir = workspace / f"project_{project_id}"
    if proj_dir.exists():
        subdirs = [d for d in proj_dir.iterdir() if d.is_dir()]
        assert len(subdirs) == 0


def test_reject_wrong_file_type(client_env):
    """Verify non-zip filenames are rejected immediately with HTTP 400."""
    client, _ = client_env
    headers = auth_headers(client, "wrong_ext@example.com")

    proj_resp = client.post("/api/projects", json={"name": "Tar project"}, headers=headers)
    project_id = proj_resp.json()["id"]

    response = client.post(
        f"/api/projects/{project_id}/upload",
        files={"file": ("app.tar.gz", b"fake tar content", "application/gzip")},
        headers=headers,
    )
    assert response.status_code == 400
    assert "Only .zip" in response.json()["detail"]


def test_reject_malformed_zip(client_env):
    """Verify corrupted/malformed ZIP file is rejected with HTTP 400 and temp cleaned up."""
    client, workspace = client_env
    headers = auth_headers(client, "corrupt@example.com")

    proj_resp = client.post("/api/projects", json={"name": "Corrupt project"}, headers=headers)
    project_id = proj_resp.json()["id"]

    corrupted_bytes = b"PK\x03\x04ThisIsNotAValidZipFileContent"
    response = client.post(
        f"/api/projects/{project_id}/upload",
        files={"file": ("app.zip", corrupted_bytes, "application/zip")},
        headers=headers,
    )
    assert response.status_code == 400
    assert "valid ZIP" in response.json()["detail"]

    proj_dir = workspace / f"project_{project_id}"
    if proj_dir.exists():
        temp_files = list(proj_dir.glob("temp_*.zip"))
        assert len(temp_files) == 0


def test_path_traversal_parent_directory_rejected(client_env):
    """Verify path traversal (e.g. ../evil.txt) is rejected and prevented from writing outside destination."""
    client, workspace = client_env
    headers = auth_headers(client, "traversal@example.com")

    proj_resp = client.post("/api/projects", json={"name": "Traversal test"}, headers=headers)
    project_id = proj_resp.json()["id"]

    files = {
        "Dockerfile": "FROM alpine",
        "../escape.txt": "escaped!",
    }
    zip_bytes = create_zip_bytes(files)

    response = client.post(
        f"/api/projects/{project_id}/upload",
        files={"file": ("malicious.zip", zip_bytes, "application/zip")},
        headers=headers,
    )
    assert response.status_code == 400
    assert "Path traversal" in response.json()["detail"]
    assert not (workspace / "escape.txt").exists()


def test_path_traversal_absolute_path_rejected(client_env):
    """Verify absolute paths inside zip entry are rejected."""
    client, _ = client_env
    headers = auth_headers(client, "abs_path@example.com")

    proj_resp = client.post("/api/projects", json={"name": "Abs path test"}, headers=headers)
    project_id = proj_resp.json()["id"]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("/etc/passwd", "root:x:0:0")
        zf.writestr("Dockerfile", "FROM alpine")
    zip_bytes = buf.getvalue()

    response = client.post(
        f"/api/projects/{project_id}/upload",
        files={"file": ("malicious_abs.zip", zip_bytes, "application/zip")},
        headers=headers,
    )
    assert response.status_code == 400
    assert "absolute" in response.json()["detail"].lower()


def test_oversized_upload_rejected(client_env, monkeypatch):
    """Verify upload exceeding MAX_UPLOAD_SIZE_BYTES is rejected with HTTP 413 and cleaned up."""
    client, workspace = client_env
    headers = auth_headers(client, "oversize@example.com")

    # Set threshold low for testing
    monkeypatch.setattr(config, "MAX_UPLOAD_SIZE_BYTES", 500)

    proj_resp = client.post("/api/projects", json={"name": "Oversize test"}, headers=headers)
    project_id = proj_resp.json()["id"]

    files = {
        "Dockerfile": "FROM alpine",
        "bigfile.dat": os.urandom(1000),
    }
    zip_bytes = create_zip_bytes(files)

    response = client.post(
        f"/api/projects/{project_id}/upload",
        files={"file": ("big.zip", zip_bytes, "application/zip")},
        headers=headers,
    )
    assert response.status_code == 413
    assert "exceeds maximum allowed size" in response.json()["detail"]

    # Verify temp file is cleaned up
    proj_dir = workspace / f"project_{project_id}"
    if proj_dir.exists():
        temp_files = list(proj_dir.glob("temp_*.zip"))
        assert len(temp_files) == 0


def test_expanded_size_limit_rejected(client_env, monkeypatch):
    """Verify decompression bomb / expanded size exceeding limit is caught during inspection."""
    client, workspace = client_env
    headers = auth_headers(client, "bomb@example.com")

    # Set expanded limit low (e.g. 5 KB)
    monkeypatch.setattr(config, "MAX_EXTRACTED_SIZE_BYTES", 5000)

    proj_resp = client.post("/api/projects", json={"name": "Bomb test"}, headers=headers)
    project_id = proj_resp.json()["id"]

    # 10 KB uncompressed data
    files = {
        "Dockerfile": "FROM alpine",
        "large_decompressed.txt": "0" * 10000,
    }
    zip_bytes = create_zip_bytes(files)

    response = client.post(
        f"/api/projects/{project_id}/upload",
        files={"file": ("bomb.zip", zip_bytes, "application/zip")},
        headers=headers,
    )
    assert response.status_code == 400
    assert "Expanded archive size exceeds maximum limit" in response.json()["detail"]


def test_excessive_file_count_rejected(client_env, monkeypatch):
    """Verify archive with excessive file count is rejected."""
    client, workspace = client_env
    headers = auth_headers(client, "files_count@example.com")

    monkeypatch.setattr(config, "MAX_FILE_COUNT", 5)

    proj_resp = client.post("/api/projects", json={"name": "Count test"}, headers=headers)
    project_id = proj_resp.json()["id"]

    files = {"Dockerfile": "FROM alpine"}
    for i in range(10):
        files[f"file_{i}.txt"] = "sample"
    zip_bytes = create_zip_bytes(files)

    response = client.post(
        f"/api/projects/{project_id}/upload",
        files={"file": ("many_files.zip", zip_bytes, "application/zip")},
        headers=headers,
    )
    assert response.status_code == 400
    assert "too many entries" in response.json()["detail"]


def test_symlink_rejected(client_env):
    """Verify symlink entry inside archive is rejected."""
    client, workspace = client_env
    headers = auth_headers(client, "symlink@example.com")

    proj_resp = client.post("/api/projects", json={"name": "Symlink test"}, headers=headers)
    project_id = proj_resp.json()["id"]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Dockerfile", "FROM alpine")
        # Create a symlink entry
        zinfo = zipfile.ZipInfo("symlink_entry")
        # 0o120000 is S_IFLNK
        zinfo.external_attr = 0o120777 << 16
        zf.writestr(zinfo, "/etc/passwd")
    zip_bytes = buf.getvalue()

    response = client.post(
        f"/api/projects/{project_id}/upload",
        files={"file": ("symlink.zip", zip_bytes, "application/zip")},
        headers=headers,
    )
    assert response.status_code == 400
    assert "symlink" in response.json()["detail"].lower()


def test_upload_requires_authentication(client_env):
    """Verify unauthenticated upload requests are rejected with HTTP 401."""
    client, _ = client_env
    zip_bytes = create_zip_bytes({"Dockerfile": "FROM alpine"})

    response = client.post(
        "/api/projects/1/upload",
        files={"file": ("app.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 401


def test_cross_user_upload_denied(client_env):
    """Verify User B cannot upload to User A's project (returns HTTP 404)."""
    client, _ = client_env
    headers_alice = auth_headers(client, "user_alice@example.com")
    headers_bob = auth_headers(client, "user_bob@example.com")

    # Alice creates a project
    proj_resp = client.post("/api/projects", json={"name": "Alice App"}, headers=headers_alice)
    alice_proj_id = proj_resp.json()["id"]

    zip_bytes = create_zip_bytes({"Dockerfile": "FROM alpine"})

    # Bob attempts upload to Alice's project
    response = client.post(
        f"/api/projects/{alice_proj_id}/upload",
        files={"file": ("app.zip", zip_bytes, "application/zip")},
        headers=headers_bob,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"
