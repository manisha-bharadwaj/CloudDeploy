from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# User & Auth Schemas
class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# Project Schemas
class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    name: str
    created_at: datetime


# Upload Schemas
class UploadResponse(BaseModel):
    message: str
    project_id: int
    upload_id: str
    extracted_files: int
    total_size_bytes: int


# Deployment Schemas
class DeploymentCreateRequest(BaseModel):
    upload_id: Optional[str] = None


class DeploymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    version: int
    status: str
    container_id: Optional[str] = None
    image_tag: Optional[str] = None
    application_port: Optional[int] = None
    application_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


class DeploymentLogsResponse(BaseModel):
    deployment_id: int
    status: str
    logs: str
