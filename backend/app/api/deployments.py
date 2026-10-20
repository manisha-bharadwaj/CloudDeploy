from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core import config
from app.core.database import get_db
from app.models.entities import Deployment, DeploymentStatus, Project, User
from app.schemas.dtos import DeploymentLogsResponse, DeploymentResponse
from app.services.deployment_service import restart_deployment, stop_deployment

router = APIRouter(prefix="/deployments", tags=["deployments"])


def format_deployment_response(deployment: Deployment) -> DeploymentResponse:
    """Helper to convert Deployment model to DeploymentResponse with application_url."""
    app_url = f"http://localhost:{deployment.application_port}" if deployment.application_port else None
    return DeploymentResponse(
        id=deployment.id,
        project_id=deployment.project_id,
        version=deployment.version,
        status=deployment.status.value,
        container_id=deployment.container_id,
        image_tag=deployment.image_tag,
        application_port=deployment.application_port,
        application_url=app_url,
        error_message=deployment.error_message,
        created_at=deployment.created_at,
        finished_at=deployment.finished_at,
    )


@router.get("/{deployment_id}", response_model=DeploymentResponse)
def get_deployment(
    deployment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve a deployment by ID with ownership scoping."""
    deployment = (
        db.query(Deployment)
        .join(Project, Deployment.project_id == Project.id)
        .filter(Deployment.id == deployment_id, Project.owner_id == current_user.id)
        .first()
    )
    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        )

    return format_deployment_response(deployment)


@router.get("/{deployment_id}/logs", response_model=DeploymentLogsResponse)
def get_deployment_logs(
    deployment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve recent bounded deployment build and container logs."""
    deployment = (
        db.query(Deployment)
        .join(Project, Deployment.project_id == Project.id)
        .filter(Deployment.id == deployment_id, Project.owner_id == current_user.id)
        .first()
    )
    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        )

    logs_content = ""
    if deployment.log_path and Path(deployment.log_path).exists():
        try:
            # Read bounded log content (last 100 KB max)
            with open(deployment.log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                logs_content = "".join(lines[-500:])  # last 500 lines
        except Exception as exc:
            logs_content = f"Error reading log file: {exc}"

    return DeploymentLogsResponse(
        deployment_id=deployment.id,
        status=deployment.status.value,
        logs=logs_content,
    )


@router.post("/{deployment_id}/stop", response_model=DeploymentResponse)
def stop_deployment_endpoint(
    deployment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stop a running deployment container."""
    deployment = (
        db.query(Deployment)
        .join(Project, Deployment.project_id == Project.id)
        .filter(Deployment.id == deployment_id, Project.owner_id == current_user.id)
        .first()
    )
    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        )

    try:
        stop_deployment(deployment, db)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop deployment: {exc}",
        )

    return format_deployment_response(deployment)


@router.post("/{deployment_id}/restart", response_model=DeploymentResponse)
def restart_deployment_endpoint(
    deployment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Restart a stopped deployment container."""
    deployment = (
        db.query(Deployment)
        .join(Project, Deployment.project_id == Project.id)
        .filter(Deployment.id == deployment_id, Project.owner_id == current_user.id)
        .first()
    )
    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        )

    if not deployment.container_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deployment does not have an associated container to restart.",
        )

    try:
        restart_deployment(deployment, db)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restart deployment: {exc}",
        )

    return format_deployment_response(deployment)
