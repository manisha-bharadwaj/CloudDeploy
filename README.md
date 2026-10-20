# CloudDeploy Lite

CloudDeploy Lite is a beginner-friendly cloud deployment platform designed to simplify deploying and managing web applications on cloud infrastructure.

## Project Structure

```text
CloudDeploy/
├── .github/
│   └── workflows/
│       └── ci.yml             # GitHub Actions CI workflow
├── backend/
│   ├── app/
│   │   ├── api/               # API routes and endpoints
│   │   ├── core/              # Config, security, and settings
│   │   ├── models/            # Database / ORM models
│   │   ├── schemas/           # Pydantic schemas / request-response DTOs
│   │   ├── services/          # Business logic and external service clients
│   │   ├── __init__.py
│   │   └── main.py            # FastAPI application entry point
│   ├── tests/                 # Backend automated test suite
│   └── requirements.txt       # Python dependencies
├── frontend/                  # React + TypeScript + Vite UI
├── sample-app/                # Sample application templates for deployment
├── docs/                      # Project documentation and specifications
├── .env.example               # Example environment variable template
├── .gitignore                 # Git ignore rules
└── README.md                  # Project overview and setup guide
```

---

## Prerequisites

Before running the project locally, ensure you have the following installed:

- **Python**: version 3.10+ (tested with Python 3.11)
- **Node.js**: version 18+ (tested with Node.js v22)
- **npm**: version 9+ (tested with npm 10.9)

---

## Local Setup & Run Guide

### 1. Environment Configuration

Copy the example environment file:

```bash
# In the repository root
cp .env.example .env
```

### 2. Backend Setup & Run

1. Navigate to the backend directory and set up a Python virtual environment:

   ```bash
   cd backend
   python -m venv .venv
   ```

2. Activate the virtual environment:
   - On Windows (PowerShell):
     ```powershell
     .venv\Scripts\Activate.ps1
     ```
   - On Windows (CMD):
     ```cmd
     .venv\Scripts\activate.bat
     ```
   - On Linux/macOS:
     ```bash
     source .venv/bin/activate
     ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Start the FastAPI development server:

   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

5. Verify the health endpoint:
   - Open your browser or run:
     ```bash
     curl http://localhost:8000/health
     ```
   - Response: `{"status":"ok"}`
   - API Docs: `http://localhost:8000/docs`

6. Run backend tests:

   ```bash
   pytest
   ```

   Database tables are automatically created on application startup via SQLAlchemy metadata. By default, SQLite stores data locally in `clouddeploy.db`, which can be customized via the `DATABASE_URL` environment variable.

   Authentication uses JWT access tokens signed with `JWT_SECRET_KEY` and passwords hashed with bcrypt:
   - `POST /api/auth/register` — Create a new user account
   - `POST /api/auth/login` — Log in and obtain JWT access token
   - `GET /api/projects` — List user's projects (Requires Bearer token)
   - `POST /api/projects` — Create a new user project (Requires Bearer token)
   - `GET /api/projects/{project_id}` — Get project by ID (Owner-scoped, returns 404 for other users' projects)
   - `POST /api/projects/{project_id}/upload` — Securely upload and extract application ZIP file (Requires Bearer token and owner access)
   - `POST /api/projects/{project_id}/deployments` — Trigger asynchronous container build and deployment (Returns HTTP 202)
   - `GET /api/deployments/{deployment_id}` — Get deployment status, container ID, and application URL
   - `GET /api/deployments/{deployment_id}/logs` — Retrieve bounded build and container runtime logs
   - `POST /api/deployments/{deployment_id}/stop` — Stop a running deployment container
   - `POST /api/deployments/{deployment_id}/restart` — Restart a stopped container and verify health

   Container & Deployment Safety:
   - Server-allocated non-conflicting host port mapping.
   - Resource-constrained execution (`--memory`, `--cpus`, `--pids-limit`).
   - Non-privileged execution without host network mode or mounted Docker sockets.
   - Automatic failure handling and container cleanup on failed health checks.

   ZIP upload safety and constraints:
   - Enforces a 25 MB compressed file limit (`MAX_UPLOAD_SIZE_BYTES`) and 100 MB expanded limit (`MAX_EXTRACTED_SIZE_BYTES`).
   - Requires a root `Dockerfile` inside the archive.
   - Detects and rejects path traversal (`..` or absolute paths), suspicious symlinks/special devices, excessive files (`MAX_FILE_COUNT`), and malformed archives.
   - Extracts into server-controlled project workspaces (`WORKSPACE_DIR`), isolated outside the frontend.

---

## Notes on Docker Integration Tests

- The test suite includes both mocked Docker interactions and a real‑Docker integration test. The real‑Docker test requires a Docker daemon to be running on the host machine; if Docker is not available, the test will be skipped.
- Uploaded applications are **trusted** to contain a valid `Dockerfile`. The system does not sandbox Docker builds beyond the built‑in resource limits (memory, CPUs, PID limits) and non‑root execution. Ensure you only upload containers you trust.


### 3. Frontend Setup & Run

1. In a separate terminal, navigate to the frontend directory:

   ```bash
   cd frontend
   ```

2. Install dependencies:

   ```bash
   npm install
   ```

3. Start the Vite development server:

   ```bash
   npm run dev
   ```

4. Open your browser and navigate to:
   ```text
   http://localhost:5173
   ```
