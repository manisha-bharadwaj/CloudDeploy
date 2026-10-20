from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core import config
from app.core.database import get_db
from app.models.entities import Deployment, DeploymentStatus, Project, User
from app.schemas.dtos import (
    DeploymentCreateRequest,
    DeploymentResponse,
    ProjectCreateRequest,
    ProjectResponse,
    UploadResponse,
)
from app.services.archive import save_and_extract_zip
from app.services.deployment_service import run_deployment_worker

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    request: ProjectCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new project owned by the authenticated user."""
    project_name = request.name.strip()
    if not project_name:
        raise HTTPException(
            status_code=422,
            detail="Project name cannot be empty",
        )

    project = Project(
        name=project_name,
        owner_id=current_user.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    return project


@router.get("", response_model=List[ProjectResponse])
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all projects owned by the authenticated user."""
    projects = (
        db.query(Project)
        .filter(Project.owner_id == current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    return projects


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a project by ID only if owned by the authenticated user. Return 404 otherwise."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.owner_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return project


@router.post("/{project_id}/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
def upload_project_zip(
    project_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload and safely extract a project ZIP archive with Dockerfile."""
    # Verify project exists and belongs to authenticated user
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.owner_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    upload_id, file_count, total_size = save_and_extract_zip(file, project.id)

    return UploadResponse(
        message="Archive uploaded and safely extracted successfully.",
        project_id=project.id,
        upload_id=upload_id,
        extracted_files=file_count,
        total_size_bytes=total_size,
    )


@router.post("/{project_id}/deployments", response_model=DeploymentResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_deployment(
    project_id: int,
    request: Optional[DeploymentCreateRequest] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Trigger a new deployment for a project from an uploaded workspace."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.owner_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    project_dir = (config.WORKSPACE_DIR / f"project_{project.id}").resolve()
    target_upload_dir: Optional[Path] = None

    if request and request.upload_id:
        target_upload_dir = (project_dir / request.upload_id).resolve()
        if not target_upload_dir.exists() or not target_upload_dir.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Specified upload directory '{request.upload_id}' not found.",
            )
    else:
        # Pick the most recent upload directory under project_dir
        if project_dir.exists():
            upload_subdirs = [
                d for d in project_dir.iterdir()
                if d.is_dir() and not d.name.startswith("temp_")
            ]
            if upload_subdirs:
                # Sort by last modified time descending
                upload_subdirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                target_upload_dir = upload_subdirs[0]

    if not target_upload_dir or not (target_upload_dir / "Dockerfile").exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid uploaded application with Dockerfile found. Please upload a ZIP archive first.",
        )

    # Compute next deployment version
    latest_deployment = (
        db.query(Deployment)
        .filter(Deployment.project_id == project.id)
        .order_by(Deployment.version.desc())
        .first()
    )
    next_version = (latest_deployment.version + 1) if latest_deployment else 1

    # Prepare deployment record
    new_deployment = Deployment(
        project_id=project.id,
        version=next_version,
        status=DeploymentStatus.QUEUED,
    )
    db.add(new_deployment)
    db.commit()
    db.refresh(new_deployment)

    # Assign log path
    log_file_path = (config.LOGS_DIR / f"deployment_{new_deployment.id}.log").resolve()
    new_deployment.log_path = str(log_file_path)
    db.commit()

    # Trigger background worker
    background_tasks.add_task(run_deployment_worker, new_deployment.id, target_upload_dir)

    return DeploymentResponse(
        id=new_deployment.id,
        project_id=new_deployment.project_id,
        version=new_deployment.version,
        status=new_deployment.status.value,
        container_id=new_deployment.container_id,
        image_tag=new_deployment.image_tag,
        application_port=new_deployment.application_port,
        application_url=None,
        error_message=new_deployment.error_message,
        created_at=new_deployment.created_at,
        finished_at=new_deployment.finished_at,
    )
