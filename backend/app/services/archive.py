import os
from pathlib import Path
import shutil
import stat
import uuid
import zipfile
from typing import Tuple

from fastapi import HTTPException, UploadFile, status

from app.core import config


class ArchiveValidationError(HTTPException):
    """Exception raised for archive validation errors."""

    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)


def is_symlink_or_special(zip_info: zipfile.ZipInfo) -> bool:
    """Check if zip member is a symbolic link or special device/FIFO file."""
    # The upper 16 bits of external_attr hold UNIX file permissions/mode
    mode = zip_info.external_attr >> 16
    if stat.S_ISLNK(mode) or stat.S_ISCHR(mode) or stat.S_ISBLK(mode) or stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode):
        return True
    return False


def save_and_extract_zip(
    upload_file: UploadFile,
    project_id: int,
) -> Tuple[str, int, int]:
    """
    Safely process, validate, and extract an uploaded application ZIP archive.

    Returns:
        (upload_id, file_count, total_extracted_size)
    """
    filename = upload_file.filename or ""
    if not filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only .zip archives are allowed.",
        )

    # Generate a unique server-controlled upload identifier and target directory
    upload_id = uuid.uuid4().hex
    project_workspace = (config.WORKSPACE_DIR / f"project_{project_id}").resolve()
    target_extract_dir = (project_workspace / upload_id).resolve()
    temp_zip_path = (project_workspace / f"temp_{upload_id}.zip").resolve()

    # Ensure parent workspace directory exists
    project_workspace.mkdir(parents=True, exist_ok=True)

    # 1. Stream file to temp disk location while enforcing MAX_UPLOAD_SIZE_BYTES
    uploaded_size = 0
    try:
        with open(temp_zip_path, "wb") as buffer:
            while True:
                chunk = upload_file.file.read(1024 * 64)  # 64 KB chunks
                if not chunk:
                    break
                uploaded_size += len(chunk)
                if uploaded_size > config.MAX_UPLOAD_SIZE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"Upload exceeds maximum allowed size of "
                            f"{config.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB."
                        ),
                    )
                buffer.write(chunk)
    except Exception:
        # Clean up temp file on write error
        if temp_zip_path.exists():
            temp_zip_path.unlink()
        raise

    # 2. Inspect ZIP archive
    try:
        if not zipfile.is_zipfile(temp_zip_path):
            raise ArchiveValidationError("Uploaded file is not a valid ZIP archive.")

        with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
            infolist = zip_ref.infolist()

            if not infolist:
                raise ArchiveValidationError("ZIP archive is empty.")

            if len(infolist) > config.MAX_FILE_COUNT:
                raise ArchiveValidationError(
                    f"ZIP archive contains too many entries ({len(infolist)}). "
                    f"Maximum allowed is {config.MAX_FILE_COUNT}."
                )

            total_uncompressed_size = 0
            has_dockerfile_at_root = False

            # Pre-extraction validation pass
            for info in infolist:
                total_uncompressed_size += info.file_size
                if total_uncompressed_size > config.MAX_EXTRACTED_SIZE_BYTES:
                    raise ArchiveValidationError(
                        f"Expanded archive size exceeds maximum limit of "
                        f"{config.MAX_EXTRACTED_SIZE_BYTES // (1024 * 1024)} MB."
                    )

                if is_symlink_or_special(info):
                    raise ArchiveValidationError(
                        f"Archive contains unsupported or unsafe special entry/symlink: {info.filename}"
                    )

                # Normalize and check path traversal
                member_path = info.filename
                # Disallow absolute paths
                if os.path.isabs(member_path) or member_path.startswith("/") or member_path.startswith("\\"):
                    raise ArchiveValidationError(f"Archive entry contains absolute path: {member_path}")

                # Check for Windows drive letter like C:
                if len(member_path) > 1 and member_path[1] == ":":
                    raise ArchiveValidationError(f"Archive entry contains drive specifier: {member_path}")

                # Path traversal check
                resolved_dest = (target_extract_dir / member_path).resolve()
                try:
                    resolved_dest.relative_to(target_extract_dir)
                except ValueError:
                    raise ArchiveValidationError(
                        f"Path traversal detected in archive entry: {member_path}"
                    )

                # Check if Dockerfile exists at root level
                clean_name = member_path.replace("\\", "/").strip("/")
                if clean_name.lower() == "dockerfile" and "/" not in clean_name:
                    has_dockerfile_at_root = True

            if not has_dockerfile_at_root:
                raise ArchiveValidationError(
                    "Missing 'Dockerfile' at the root of the archive. A root Dockerfile is required."
                )

            # 3. Safe extraction
            target_extract_dir.mkdir(parents=True, exist_ok=False)

            file_count = 0
            for info in infolist:
                # Re-verify destination confinement before extracting
                dest_path = (target_extract_dir / info.filename).resolve()
                try:
                    dest_path.relative_to(target_extract_dir)
                except ValueError:
                    raise ArchiveValidationError(f"Extraction path escape detected: {info.filename}")

                if info.is_dir():
                    dest_path.mkdir(parents=True, exist_ok=True)
                else:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    with zip_ref.open(info, "r") as source, open(dest_path, "wb") as target:
                        shutil.copyfileobj(source, target)
                    file_count += 1

            return upload_id, file_count, total_uncompressed_size

    except Exception:
        # Clean up any partially extracted directories
        if target_extract_dir.exists():
            shutil.rmtree(target_extract_dir, ignore_errors=True)
        raise

    finally:
        # Always remove temporary zip file after extraction attempt
        if temp_zip_path.exists():
            try:
                temp_zip_path.unlink()
            except OSError:
                pass
