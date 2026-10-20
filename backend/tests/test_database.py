import pytest
from sqlalchemy import create_engine, inspect, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone

from app.core.database import Base
from app.models.entities import User, Project, Deployment, DeploymentStatus


@pytest.fixture
def db_session(tmp_path):
    """Fixture providing an isolated SQLite database session for each test."""
    test_db_file = tmp_path / "test.db"
    test_db_url = f"sqlite:///{test_db_file}"

    test_engine = create_engine(
        test_db_url,
        connect_args={"check_same_thread": False},
    )

    # Enable SQLite foreign key support
    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create tables
    Base.metadata.create_all(bind=test_engine)

    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestSession()

    try:
        yield session, test_engine
    finally:
        session.close()
        test_engine.dispose()


def test_table_creation(db_session):
    """Verify that users, projects, and deployments tables are created."""
    _, engine = db_session
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    assert "users" in table_names
    assert "projects" in table_names
    assert "deployments" in table_names

    user_cols = {col["name"] for col in inspector.get_columns("users")}
    assert {"id", "email", "password_hash", "created_at"}.issubset(user_cols)

    project_cols = {col["name"] for col in inspector.get_columns("projects")}
    assert {"id", "owner_id", "name", "created_at"}.issubset(project_cols)

    deployment_cols = {col["name"] for col in inspector.get_columns("deployments")}
    assert {
        "id",
        "project_id",
        "version",
        "status",
        "container_id",
        "image_tag",
        "application_port",
        "log_path",
        "error_message",
        "created_at",
        "finished_at",
    }.issubset(deployment_cols)


def test_user_persistence_and_unique_constraint(db_session):
    """Verify User model persistence and email uniqueness."""
    session, _ = db_session

    user1 = User(email="test@example.com", password_hash="hashed_pw_123")
    session.add(user1)
    session.commit()
    session.refresh(user1)

    assert user1.id is not None
    assert user1.email == "test@example.com"
    assert user1.password_hash == "hashed_pw_123"
    assert isinstance(user1.created_at, datetime)

    # Attempting to add duplicate email should violate unique constraint
    user2 = User(email="test@example.com", password_hash="another_hash")
    session.add(user2)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_project_persistence_and_relationships(db_session):
    """Verify Project creation, foreign key to user, and relationship navigation."""
    session, _ = db_session

    user = User(email="owner@example.com", password_hash="hashed_secret")
    session.add(user)
    session.commit()
    session.refresh(user)

    project = Project(owner_id=user.id, name="My Express App")
    session.add(project)
    session.commit()
    session.refresh(project)

    assert project.id is not None
    assert project.name == "My Express App"
    assert project.owner_id == user.id
    assert project.owner.email == "owner@example.com"
    assert len(user.projects) == 1
    assert user.projects[0].name == "My Express App"


def test_foreign_key_violation_for_project(db_session):
    """Verify that foreign keys are enforced: Project cannot reference non-existent User."""
    session, _ = db_session

    invalid_project = Project(owner_id=999999, name="Ghost Project")
    session.add(invalid_project)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_deployment_persistence_and_relationships(db_session):
    """Verify Deployment creation with nullable fields, enum status, and project relation."""
    session, _ = db_session

    user = User(email="dev@example.com", password_hash="hashed_secret")
    session.add(user)
    session.commit()

    project = Project(owner_id=user.id, name="Test Service")
    session.add(project)
    session.commit()

    deployment = Deployment(
        project_id=project.id,
        version=1,
        status=DeploymentStatus.BUILDING,
        container_id="c_12345",
        image_tag="test-service:v1",
        application_port=3000,
        log_path="/var/log/deployments/1.log",
        error_message=None,
        finished_at=None,
    )
    session.add(deployment)
    session.commit()
    session.refresh(deployment)

    assert deployment.id is not None
    assert deployment.version == 1
    assert deployment.status == DeploymentStatus.BUILDING
    assert deployment.container_id == "c_12345"
    assert deployment.image_tag == "test-service:v1"
    assert deployment.application_port == 3000
    assert deployment.log_path == "/var/log/deployments/1.log"
    assert deployment.error_message is None
    assert deployment.finished_at is None
    assert isinstance(deployment.created_at, datetime)

    # Verify relationship navigation
    assert deployment.project.name == "Test Service"
    assert len(project.deployments) == 1
    assert project.deployments[0].id == deployment.id


def test_foreign_key_violation_for_deployment(db_session):
    """Verify that foreign keys are enforced: Deployment cannot reference non-existent Project."""
    session, _ = db_session

    invalid_deployment = Deployment(
        project_id=888888,
        version=1,
        status=DeploymentStatus.QUEUED,
    )
    session.add(invalid_deployment)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_deployment_statuses(db_session):
    """Verify all required statuses can be assigned and saved."""
    session, _ = db_session

    user = User(email="admin@example.com", password_hash="hashed_secret")
    session.add(user)
    session.commit()

    project = Project(owner_id=user.id, name="Lifecycle Project")
    session.add(project)
    session.commit()

    statuses = [
        DeploymentStatus.QUEUED,
        DeploymentStatus.BUILDING,
        DeploymentStatus.RUNNING,
        DeploymentStatus.FAILED,
        DeploymentStatus.STOPPED,
    ]

    for idx, st in enumerate(statuses, start=1):
        dep = Deployment(project_id=project.id, version=idx, status=st)
        session.add(dep)
    session.commit()

    retrieved = session.query(Deployment).filter_by(project_id=project.id).all()
    assert len(retrieved) == 5
    retrieved_statuses = [d.status for d in retrieved]
    assert retrieved_statuses == statuses


def test_cascade_deletion(db_session):
    """Verify cascade delete from User -> Project -> Deployment."""
    session, _ = db_session

    user = User(email="cascade@example.com", password_hash="pass")
    session.add(user)
    session.commit()

    project = Project(owner_id=user.id, name="Cascade Project")
    session.add(project)
    session.commit()

    deployment = Deployment(project_id=project.id, version=1, status=DeploymentStatus.RUNNING)
    session.add(deployment)
    session.commit()

    # Delete user
    session.delete(user)
    session.commit()

    assert session.query(User).filter_by(email="cascade@example.com").first() is None
    assert session.query(Project).filter_by(name="Cascade Project").first() is None
    assert session.query(Deployment).count() == 0
