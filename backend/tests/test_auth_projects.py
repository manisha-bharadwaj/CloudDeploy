from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.main import app


@pytest.fixture
def client_and_db(tmp_path):
    """Fixture providing a TestClient configured with an isolated temporary SQLite database."""
    test_db_file = tmp_path / "test_api.db"
    test_db_url = f"sqlite:///{test_db_file}"

    test_engine = create_engine(
        test_db_url,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create tables
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
        yield client, TestSession

    app.dependency_overrides.clear()
    test_engine.dispose()


def test_password_hashing_utilities():
    """Verify bcrypt password hashing and verification."""
    password = "supersecretpassword"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrongpassword", hashed) is False


def test_register_success(client_and_db):
    """Verify user registration returns HTTP 201 without password fields."""
    client, _ = client_and_db

    response = client.post(
        "/api/auth/register",
        json={"email": "newuser@example.com", "password": "securepassword123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert "id" in data
    assert "created_at" in data
    assert "password" not in data
    assert "password_hash" not in data


def test_register_duplicate_email(client_and_db):
    """Verify registering duplicate email returns HTTP 400."""
    client, _ = client_and_db

    payload = {"email": "duplicate@example.com", "password": "password123"}
    resp1 = client.post("/api/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = client.post("/api/auth/register", json=payload)
    assert resp2.status_code == 400
    assert "already registered" in resp2.json()["detail"].lower()


def test_register_validation_error(client_and_db):
    """Verify registering with invalid email or short password returns HTTP 422."""
    client, _ = client_and_db

    # Short password (< 6 chars)
    resp = client.post("/api/auth/register", json={"email": "val@example.com", "password": "123"})
    assert resp.status_code == 422

    # Invalid email format
    resp2 = client.post("/api/auth/register", json={"email": "not-an-email", "password": "securepassword"})
    assert resp2.status_code == 422


def test_login_success_and_token_generation(client_and_db):
    """Verify login returns valid signed JWT and user info without password hash."""
    client, _ = client_and_db

    client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "correctpassword"},
    )

    response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "correctpassword"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "user@example.com"
    assert "password" not in data["user"]
    assert "password_hash" not in data["user"]


def test_login_invalid_credentials(client_and_db):
    """Verify login with wrong password or nonexistent email returns HTTP 401."""
    client, _ = client_and_db

    client.post(
        "/api/auth/register",
        json={"email": "loginfail@example.com", "password": "validpassword"},
    )

    # Wrong password
    resp1 = client.post(
        "/api/auth/login",
        json={"email": "loginfail@example.com", "password": "wrongpassword"},
    )
    assert resp1.status_code == 401

    # Nonexistent user
    resp2 = client.post(
        "/api/auth/login",
        json={"email": "nonexistent@example.com", "password": "anypassword"},
    )
    assert resp2.status_code == 401


def test_project_endpoints_require_authentication(client_and_db):
    """Verify /api/projects routes reject unauthenticated requests with HTTP 401."""
    client, _ = client_and_db

    # Missing token
    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/projects", json={"name": "No Auth"}).status_code == 401
    assert client.get("/api/projects/1").status_code == 401

    # Invalid token
    bad_headers = {"Authorization": "Bearer invalid.jwt.token"}
    assert client.get("/api/projects", headers=bad_headers).status_code == 401


def test_project_endpoints_reject_expired_token(client_and_db):
    """Verify expired JWT tokens are rejected with HTTP 401."""
    client, _ = client_and_db

    expired_token = create_access_token(
        data={"sub": "1"},
        expires_delta=timedelta(minutes=-10),
    )
    headers = {"Authorization": f"Bearer {expired_token}"}
    response = client.get("/api/projects", headers=headers)
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_project_creation_and_listing(client_and_db):
    """Verify authenticated user can create and list their own projects."""
    client, _ = client_and_db

    # Register and login User A
    client.post("/api/auth/register", json={"email": "usera@example.com", "password": "passwordA123"})
    login_resp = client.post("/api/auth/login", json={"email": "usera@example.com", "password": "passwordA123"})
    token_a = login_resp.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Create project 1
    create_resp1 = client.post("/api/projects", json={"name": "Alpha Service"}, headers=headers_a)
    assert create_resp1.status_code == 201
    p1 = create_resp1.json()
    assert p1["name"] == "Alpha Service"
    assert p1["id"] is not None

    # Create project 2
    create_resp2 = client.post("/api/projects", json={"name": "Beta API"}, headers=headers_a)
    assert create_resp2.status_code == 201

    # List projects
    list_resp = client.get("/api/projects", headers=headers_a)
    assert list_resp.status_code == 200
    projects = list_resp.json()
    assert len(projects) == 2
    names = [p["name"] for p in projects]
    assert "Alpha Service" in names
    assert "Beta API" in names


def test_cross_user_project_access_denial(client_and_db):
    """Verify User B cannot access or list User A's projects, returning 404 for specific ID."""
    client, _ = client_and_db

    # Register and login User A
    client.post("/api/auth/register", json={"email": "alice@example.com", "password": "alicepassword"})
    alice_login = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "alicepassword"})
    token_a = alice_login.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Register and login User B
    client.post("/api/auth/register", json={"email": "bob@example.com", "password": "bobpassword"})
    bob_login = client.post("/api/auth/login", json={"email": "bob@example.com", "password": "bobpassword"})
    token_b = bob_login.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Alice creates a project
    alice_project = client.post("/api/projects", json={"name": "Alice Private Project"}, headers=headers_a).json()
    alice_project_id = alice_project["id"]

    # Bob lists projects -> should be empty
    bob_list = client.get("/api/projects", headers=headers_b)
    assert bob_list.status_code == 200
    assert len(bob_list.json()) == 0

    # Bob attempts to get Alice's project -> MUST return HTTP 404
    bob_get_alice_proj = client.get(f"/api/projects/{alice_project_id}", headers=headers_b)
    assert bob_get_alice_proj.status_code == 404
    assert bob_get_alice_proj.json()["detail"] == "Project not found"

    # Alice CAN get her own project
    alice_get_own_proj = client.get(f"/api/projects/{alice_project_id}", headers=headers_a)
    assert alice_get_own_proj.status_code == 200
    assert alice_get_own_proj.json()["id"] == alice_project_id


def test_project_validation_errors(client_and_db):
    """Verify empty or whitespace project names are rejected with HTTP 422."""
    client, _ = client_and_db

    client.post("/api/auth/register", json={"email": "tester@example.com", "password": "password123"})
    login_resp = client.post("/api/auth/login", json={"email": "tester@example.com", "password": "password123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Empty string
    res1 = client.post("/api/projects", json={"name": ""}, headers=headers)
    assert res1.status_code == 422

    # Whitespace only
    res2 = client.post("/api/projects", json={"name": "   "}, headers=headers)
    assert res2.status_code == 422


def test_production_secret_requirement(monkeypatch):
    """Verify that in production environment, missing JWT_SECRET_KEY raises ValueError."""
    import importlib
    from app.core import config

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(ValueError, match="JWT_SECRET_KEY environment variable is required"):
        importlib.reload(config)

    # Reset
    monkeypatch.setenv("ENVIRONMENT", "development")
    importlib.reload(config)
