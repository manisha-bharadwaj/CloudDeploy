from datetime import datetime, timezone
from pathlib import Path
import threading
import os
from typing import Optional

from sqlalchemy.orm import Session

from app.core import config
from app.core.database import SessionLocal
from app.models.entities import Deployment, DeploymentStatus, Project
from app.services import docker_service

# Lock for sequential MVP background deployments
deployment_lock = threading.Lock()


def run_deployment_worker(
    deployment_id: int,
    workspace_dir: Path,
) -> None:
    """
    Background worker that builds, runs, and health-checks a container.
    Always ensures the Deployment does not remain in 'building' or 'queued'.
    """
    with deployment_lock:
        db: Session = SessionLocal()
        deployment: Optional[Deployment] = None
        try:
            deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
            if not deployment:
                return

            # Transition to BUILDING
            deployment.status = DeploymentStatus.BUILDING
            db.commit()

            # Ensure log file exists
            log_file = Path(deployment.log_path)
            log_file.parent.mkdir(parents=True, exist_ok=True)
            # Log start of deployment
            _append_log(log_file, f"--- [Deployment {deployment.id} started at {datetime.now(timezone.utc).isoformat()}] ---\n")

            image_tag = f"clouddeploy-proj-{deployment.project_id}-v{deployment.version}:latest"
            container_name = f"clouddeploy-proj-{deployment.project_id}-v{deployment.version}"

            deployment.image_tag = image_tag
            db.commit()

            # 1. Build image
            docker_service.docker_client.build_image(workspace_dir, image_tag, log_file)

            # 2. Allocate host port and read container internal port
            host_port = docker_service.allocate_free_port()
            container_port = docker_service.detect_exposed_port(workspace_dir / "Dockerfile", default_port=8080)

            # Clean up any existing container with same name
            try:
                docker_service.docker_client.remove_container(container_name, force=True)
            except Exception:
                pass

            # 3. Start container
            container_id = docker_service.docker_client.run_container(
                image_tag=image_tag,
                container_name=container_name,
                host_port=host_port,
                container_port=container_port,
            )

            deployment.container_id = container_name
            deployment.application_port = host_port
            db.commit()

            # 4. Health check
            is_healthy = docker_service.wait_for_health_check(
                port=host_port,
                path="/health",
                timeout_seconds=config.DEPLOYMENT_HEALTHCHECK_TIMEOUT_SECONDS,
            )

            if not is_healthy:
                # Capture recent container logs
                container_logs = docker_service.docker_client.get_container_logs(container_name)
                _append_log(log_file, f"\n--- [HEALTH CHECK TIMEOUT] ---\n{container_logs}\n")

                # Clean up failed container and release port
                docker_service.docker_client.remove_container(container_name, force=True)
                try:
                    docker_service.release_port(host_port)
                except Exception:
                    pass

                deployment.status = DeploymentStatus.FAILED
                deployment.error_message = (
                    f"Health check failed: application did not respond with HTTP 200 on port {host_port}/health "
                    f"within {config.DEPLOYMENT_HEALTHCHECK_TIMEOUT_SECONDS}s."
                )
                deployment.finished_at = datetime.now(timezone.utc)
                db.commit()
                return

            # Success -> RUNNING
            deployment.status = DeploymentStatus.RUNNING
            deployment.finished_at = datetime.now(timezone.utc)
            _append_log(log_file, f"\n--- [Deployment healthy and running on port {host_port}] ---\n")
            db.commit()

        except docker_service.DockerCommandError as exc:
            if deployment:
                deployment.status = DeploymentStatus.FAILED
                deployment.error_message = exc.message
                deployment.finished_at = datetime.now(timezone.utc)
                db.commit()
                # Append error to log with size enforcement
                if deployment.log_path:
                    _append_log(deployment.log_path, f"\n--- [DEPLOYMENT ERROR] ---\n{exc.message}\n{exc.stderr}\n")
                # Release port if allocated
                if deployment.application_port:
                    try:
                        docker_service.release_port(deployment.application_port)
                    except Exception:
                        pass
        except Exception as exc:
            if deployment:
                deployment.status = DeploymentStatus.FAILED
                deployment.error_message = f"Unexpected deployment error: {exc}"
                deployment.finished_at = datetime.now(timezone.utc)
                db.commit()
                if deployment.log_path:
                    _append_log(deployment.log_path, f"\n--- [UNEXPECTED ERROR] ---\n{exc}\n")
                if deployment.application_port:
                    try:
                        docker_service.release_port(deployment.application_port)
                    except Exception:
                        pass
        finally:
            db.close()

# Helper to enforce max log file size (5 MiB)
_MAX_LOG_SIZE = 5 * 1024 * 1024  # 5 MiB

def _append_log(log_path: str, content: str) -> None:
    """Append to log file and truncate if it exceeds max size.

    Keeps the most recent bytes up to the size limit.
    """
    # Ensure directory exists
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    # Append content
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(content)
    # Truncate if needed
    try:
        size = os.path.getsize(log_path)
        if size > _MAX_LOG_SIZE:
            # Keep last _MAX_LOG_SIZE bytes
            with open(log_path, "rb+") as f:
                f.seek(-_MAX_LOG_SIZE, os.SEEK_END)
                tail = f.read()
                f.seek(0)
                f.truncate()
                f.write(tail)
    except Exception:
        pass

def stop_deployment(deployment: Deployment, db: Session) -> None:
    """Stop running deployment container and update status to STOPPED.
    Also release allocated host port.
    """
    if deployment.container_id:
        docker_service.docker_client.stop_container(deployment.container_id)
    # Release port if allocated
    if deployment.application_port:
        try:
            docker_service.release_port(deployment.application_port)
        except Exception:
            pass
    deployment.status = DeploymentStatus.STOPPED
    db.commit()
    db.refresh(deployment)


def restart_deployment(deployment: Deployment, db: Session) -> None:
    """Restart stopped deployment container and verify health."""
    if not deployment.container_id:
        raise ValueError("Cannot restart deployment without container identifier.")

    docker_service.docker_client.start_container(deployment.container_id)

    # Re-verify health if application port is known
    if deployment.application_port:
        is_healthy = docker_service.wait_for_health_check(
            port=deployment.application_port,
            path="/health",
            timeout_seconds=config.DEPLOYMENT_HEALTHCHECK_TIMEOUT_SECONDS,
        )
        if not is_healthy:
            deployment.status = DeploymentStatus.FAILED
            deployment.error_message = "Restart failed: container did not pass health check."
            db.commit()
            db.refresh(deployment)
            return

    deployment.status = DeploymentStatus.RUNNING
    db.commit()
    db.refresh(deployment)
