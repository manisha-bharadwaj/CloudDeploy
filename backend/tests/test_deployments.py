import io
from pathlib import Path
import zipfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core import config
from app.core.database import Base, get_db
from app.main import app
from app.models.entities import Deployment, DeploymentStatus
from app.services import deployment_service, docker_service
from app.services.docker_service import DockerCommandError


class MockDockerClient:
    """Mock DockerClientWrapper for deterministic, non-Docker environments."""

    def __init__(self):
        self.build_called = False
        self.run_called = False
        self.stop_called = False
        self.start_called = False
        self.remove_called = False
        self.fail_build = False
        self.fail_run = False
        self.fail_health = False
        self.containers = {}
        self.logs_content = "Mock build output line 1\nMock build output line 2\nApplication ready."

    def build_image(self, build_dir: Path, image_tag: str, log_file_path: Path):
        self.build_called = True
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write(f"\n[MOCK BUILD] Building {image_tag} from {build_dir}\n")
            f.write(self.logs_content + "\n")
        if self.fail_build:
            raise DockerCommandError("Mock build step failed", stderr="Syntax error in Dockerfile", exit_code=1)

    def run_container(self, image_tag: str, container_name: str, host_port: int, container_port: int = 8080):
        self.run_called = True
        if self.fail_run:
            raise DockerCommandError("Mock run step failed", stderr="Port collision or error", exit_code=1)
        self.containers[container_name] = {"status": "running", "port": host_port}
        return f"mock_cid_{container_name}"

    def stop_container(self, container_identifier: str, timeout_seconds: int = 5):
        self.stop_called = True
        if container_identifier in self.containers:
            self.containers[container_identifier]["status"] = "stopped"

    def start_container(self, container_identifier: str):
        self.start_called = True
        if container_identifier in self.containers:
            self.containers[container_identifier]["status"] = "running"

    def remove_container(self, container_identifier: str, force: bool = True):
        self.remove_called = True
        self.containers.pop(container_identifier, None)

    def get_container_logs(self, container_identifier: str, tail: int = 500):
        return f"[MOCK CONTAINER LOGS for {container_identifier}]\nServer started."

    def inspect_container_running(self, container_identifier: str):
        return self.containers.get(container_identifier, {}).get("status") == "running"


def create_sample_zip_bytes() -> bytes:
    """Create a sample ZIP archive with a root Dockerfile and app.py."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Dockerfile", "FROM python:3.11-slim\nEXPOSE 8080\nCMD [\"python\", \"app.py\"]")
        zf.writestr("app.py", "print('sample app running')")
    return buf.getvalue()


@pytest.fixture
def mock_docker(monkeypatch):
    """Fixture replacing global docker_client with mock and stubbing wait_for_health_check."""
    mock = MockDockerClient()
    monkeypatch.setattr(docker_service, "docker_client", mock)

    # Stub wait_for_health_check to return True unless fail_health is set
    def mock_health(port, path="/health", timeout_seconds=30):
        return not mock.fail_health

    monkeypatch.setattr(docker_service, "wait_for_health_check", mock_health)
    return mock


@pytest.fixture
def client_env(tmp_path, monkeypatch):
    """Fixture providing TestClient with temporary DB and directories."""
    test_db_file = tmp_path / "test_deploy.db"
    test_db_url = f"sqlite:///{test_db_file}"

    test_workspace = tmp_path / "workspaces"
    test_workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "WORKSPACE_DIR", test_workspace)

    test_logs = tmp_path / "logs"
    test_logs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "LOGS_DIR", test_logs)

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
    monkeypatch.setattr(deployment_service, "SessionLocal", TestSession)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client, TestSession, test_workspace, test_logs

    app.dependency_overrides.clear()
    test_engine.dispose()


def auth_headers(client, email="deployer@example.com", password="password123"):
    client.post("/api/auth/register", json={"email": email, "password": password})
    login_resp = client.post("/api/auth/login", json={"email": email, "password": password})
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_trigger_deployment_success(client_env, mock_docker):
    """Verify triggering deployment builds, runs, marks RUNNING, and assigns port/URL."""
    client, SessionLocal, _, _ = client_env
    headers = auth_headers(client, "alice_deploy@example.com")

    # Create project & upload valid ZIP
    proj_resp = client.post("/api/projects", json={"name": "Alice Deploy Proj"}, headers=headers)
    project_id = proj_resp.json()["id"]

    zip_bytes = create_sample_zip_bytes()
    upload_resp = client.post(
        f"/api/projects/{project_id}/upload",
        files={"file": ("app.zip", zip_bytes, "application/zip")},
        headers=headers,
    )
    assert upload_resp.status_code == 201

    # Trigger deployment (request accepted 202)
    deploy_resp = client.post(f"/api/projects/{project_id}/deployments", headers=headers)
    assert deploy_resp.status_code == 202
    data = deploy_resp.json()
    deployment_id = data["id"]
    assert data["version"] == 1

    # In TestClient, BackgroundTasks run synchronously before request finishes
    # Query final status
    status_resp = client.get(f"/api/deployments/{deployment_id}", headers=headers)
    assert status_resp.status_code == 200
    dep_data = status_resp.json()
    assert dep_data["status"] == "running"
    assert dep_data["application_port"] is not None
    assert dep_data["application_url"] == f"http://localhost:{dep_data['application_port']}"
    assert dep_data["container_id"] == f"clouddeploy-proj-{project_id}-v1"
    assert mock_docker.build_called is True
    assert mock_docker.run_called is True


def test_trigger_deployment_failed_build(client_env, mock_docker):
    """Verify build failure transitions status to FAILED and stores error message."""
    client, _, _, _ = client_env
    headers = auth_headers(client, "build_fail@example.com")
    mock_docker.fail_build = True

    proj_resp = client.post("/api/projects", json={"name": "Fail Build Proj"}, headers=headers)
    project_id = proj_resp.json()["id"]

    client.post(
        f"/api/projects/{project_id}/upload",
        files={"file": ("app.zip", create_sample_zip_bytes(), "application/zip")},
        headers=headers,
    )

    deploy_resp = client.post(f"/api/projects/{project_id}/deployments", headers=headers)
    deployment_id = deploy_resp.json()["id"]

    status_resp = client.get(f"/api/deployments/{deployment_id}", headers=headers)
    dep_data = status_resp.json()
    assert dep_data["status"] == "failed"
    assert "Mock build step failed" in dep_data["error_message"]


def test_trigger_deployment_failed_health_check(client_env, mock_docker):
    """Verify health check failure transitions status to FAILED and removes container."""
    client, _, _, _ = client_env
    headers = auth_headers(client, "health_fail@example.com")
    mock_docker.fail_health = True

    proj_resp = client.post("/api/projects", json={"name": "Fail Health Proj"}, headers=headers)
    project_id = proj_resp.json()["id"]

    client.post(
        f"/api/projects/{project_id}/upload",
        files={"file": ("app.zip", create_sample_zip_bytes(), "application/zip")},
        headers=headers,
    )

    deploy_resp = client.post(f"/api/projects/{project_id}/deployments", headers=headers)
    deployment_id = deploy_resp.json()["id"]

    status_resp = client.get(f"/api/deployments/{deployment_id}", headers=headers)
    dep_data = status_resp.json()
    assert dep_data["status"] == "failed"
    assert "Health check failed" in dep_data["error_message"]
    assert mock_docker.remove_called is True


def test_get_deployment_logs(client_env, mock_docker):
    """Verify retrieving bounded build and execution logs."""
    client, _, _, _ = client_env
    headers = auth_headers(client, "logs_user@example.com")

    proj_resp = client.post("/api/projects", json={"name": "Logs Proj"}, headers=headers)
    project_id = proj_resp.json()["id"]

    client.post(
        f"/api/projects/{project_id}/upload",
        files={"file": ("app.zip", create_sample_zip_bytes(), "application/zip")},
        headers=headers,
    )

    deploy_resp = client.post(f"/api/projects/{project_id}/deployments", headers=headers)
    deployment_id = deploy_resp.json()["id"]

    logs_resp = client.get(f"/api/deployments/{deployment_id}/logs", headers=headers)
    assert logs_resp.status_code == 200
    logs_data = logs_resp.json()
    assert logs_data["deployment_id"] == deployment_id
    assert "Mock build output line 1" in logs_data["logs"]


def test_stop_and_restart_deployment(client_env, mock_docker):
    """Verify stopping and restarting a running deployment."""
    client, _, _, _ = client_env
    headers = auth_headers(client, "stop_restart@example.com")

    proj_resp = client.post("/api/projects", json={"name": "Lifecycle Proj"}, headers=headers)
    project_id = proj_resp.json()["id"]

    client.post(
        f"/api/projects/{project_id}/upload",
        files={"file": ("app.zip", create_sample_zip_bytes(), "application/zip")},
        headers=headers,
    )

    deploy_resp = client.post(f"/api/projects/{project_id}/deployments", headers=headers)
    deployment_id = deploy_resp.json()["id"]

    # Stop container
    stop_resp = client.post(f"/api/deployments/{deployment_id}/stop", headers=headers)
    assert stop_resp.status_code == 200
    assert stop_resp.json()["status"] == "stopped"
    assert mock_docker.stop_called is True

    # Restart container
    restart_resp = client.post(f"/api/deployments/{deployment_id}/restart", headers=headers)
    assert restart_resp.status_code == 200
    assert restart_resp.json()["status"] == "running"
    assert mock_docker.start_called is True


def test_deployments_cross_user_access_denied(client_env, mock_docker):
    """Verify User B cannot view, log, stop, or restart User A's deployment (returns HTTP 404)."""
    client, _, _, _ = client_env
    headers_alice = auth_headers(client, "alice_owner@example.com")
    headers_bob = auth_headers(client, "bob_attacker@example.com")

    proj_resp = client.post("/api/projects", json={"name": "Alice Secret Proj"}, headers=headers_alice)
    alice_proj_id = proj_resp.json()["id"]

    client.post(
        f"/api/projects/{alice_proj_id}/upload",
        files={"file": ("app.zip", create_sample_zip_bytes(), "application/zip")},
        headers=headers_alice,
    )

    deploy_resp = client.post(f"/api/projects/{alice_proj_id}/deployments", headers=headers_alice)
    alice_dep_id = deploy_resp.json()["id"]

    # Bob attempts GET
    assert client.get(f"/api/deployments/{alice_dep_id}", headers=headers_bob).status_code == 404
    # Bob attempts logs
    assert client.get(f"/api/deployments/{alice_dep_id}/logs", headers=headers_bob).status_code == 404
    # Bob attempts stop
    assert client.post(f"/api/deployments/{alice_dep_id}/stop", headers=headers_bob).status_code == 404
    # Bob attempts restart
    assert client.post(f"/api/deployments/{alice_dep_id}/restart", headers=headers_bob).status_code == 404


def test_trigger_deployment_without_upload_rejected(client_env):
    """Verify triggering deployment on empty project without uploads returns HTTP 400."""
    client, _, _, _ = client_env
    headers = auth_headers(client, "empty_proj@example.com")

    proj_resp = client.post("/api/projects", json={"name": "Empty Proj"}, headers=headers)
    project_id = proj_resp.json()["id"]

    response = client.post(f"/api/projects/{project_id}/deployments", headers=headers)
    assert response.status_code == 400
    assert "No valid uploaded application" in response.json()["detail"]


@pytest.mark.skipif(
    not docker_service.DockerClientWrapper.is_docker_available(),
    reason="Real Docker daemon is not running or available on this system.",
)
def test_real_docker_integration(client_env):
    """Optional real Docker integration test when Docker daemon is operational."""
    client, _, _, _ = client_env
    headers = auth_headers(client, "real_docker@example.com")

    proj_resp = client.post("/api/projects", json={"name": "Real Docker App"}, headers=headers)
    project_id = proj_resp.json()["id"]

    # Upload actual sample-app
    sample_app_dir = Path(__file__).resolve().parent.parent.parent / "sample-app"
    sample_zip_bytes = io.BytesIO()
    with zipfile.ZipFile(sample_zip_bytes, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(sample_app_dir / "Dockerfile", arcname="Dockerfile")
        zf.write(sample_app_dir / "app.py", arcname="app.py")

    client.post(
        f"/api/projects/{project_id}/upload",
        files={"file": ("sample.zip", sample_zip_bytes.getvalue(), "application/zip")},
        headers=headers,
    )

    deploy_resp = client.post(f"/api/projects/{project_id}/deployments", headers=headers)
    assert deploy_resp.status_code == 202
    deployment_id = deploy_resp.json()["id"]

    dep = client.get(f"/api/deployments/{deployment_id}", headers=headers).json()
    assert dep["status"] == "running"
    assert dep["application_port"] is not None

    # Stop container
    stop_res = client.post(f"/api/deployments/{deployment_id}/stop", headers=headers)
    assert stop_res.status_code == 200
    assert stop_res.json()["status"] == "stopped"
