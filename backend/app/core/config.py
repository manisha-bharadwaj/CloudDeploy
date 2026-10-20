import os
from pathlib import Path

# Base backend directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    db_path = BASE_DIR / "clouddeploy.db"
    DATABASE_URL = f"sqlite:///{db_path}"

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

# Security & JWT configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    if ENVIRONMENT == "production":
        raise ValueError("JWT_SECRET_KEY environment variable is required in production environment.")
    JWT_SECRET_KEY = "insecure-dev-secret-key-change-in-production"

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Storage & Upload limits
MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(25 * 1024 * 1024)))  # 25 MB
MAX_EXTRACTED_SIZE_BYTES = int(os.getenv("MAX_EXTRACTED_SIZE_BYTES", str(100 * 1024 * 1024)))  # 100 MB
MAX_FILE_COUNT = int(os.getenv("MAX_FILE_COUNT", "1000"))

# Upload workspace directory (server-controlled, outside frontend)
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", str(BASE_DIR / "workspaces"))).resolve()
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

# Deployment logs directory
LOGS_DIR = Path(os.getenv("LOGS_DIR", str(BASE_DIR / "logs"))).resolve()
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Port allocation range for deployed containers
PORT_RANGE_START = int(os.getenv("PORT_RANGE_START", "8001"))
PORT_RANGE_END = int(os.getenv("PORT_RANGE_END", "8050"))

# Container resource limits
CONTAINER_MEMORY_LIMIT = os.getenv("CONTAINER_MEMORY_LIMIT", "256m")
CONTAINER_CPUS_LIMIT = float(os.getenv("CONTAINER_CPUS_LIMIT", "0.5"))
CONTAINER_PIDS_LIMIT = int(os.getenv("CONTAINER_PIDS_LIMIT", "100"))

# Health check timeout in seconds
DEPLOYMENT_HEALTHCHECK_TIMEOUT_SECONDS = int(
    os.getenv("DEPLOYMENT_HEALTHCHECK_TIMEOUT_SECONDS", "30")
)
