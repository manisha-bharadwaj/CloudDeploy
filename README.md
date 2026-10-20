# CloudDeploy 

### Containerized Application Deployment Platform

CloudDeploy is a self-service deployment platform that lets authenticated users create projects, upload application source code as ZIP archives, and manage Docker-based deployments through a web dashboard.

The project focuses on backend engineering, REST API design, containerization, authentication, deployment lifecycle management, and automated testing.

## Features

- **User Authentication:** Registration, login, password hashing, and JWT-based authentication.
- **Project Management:** Create, list, and access user-owned projects.
- **Secure ZIP Uploads:** Validate uploaded archives, enforce file and size limits, require a root-level Dockerfile, and reject unsafe archive paths.
- **Docker Deployment:** Build images and manage application containers through the backend.
- **Deployment Monitoring:** Track deployment status, inspect logs, and view application URLs.
- **Container Controls:** Stop and restart deployments, with resource restrictions and health checks.
- **Web Dashboard:** React and TypeScript interface with project management, uploads, deployment controls, and error handling.
- **Persistent Storage:** SQLite database for users, projects, and deployment records.

## Tech Stack

| Layer | Technologies |
|---|---|
| Frontend | React, TypeScript, Vite, CSS |
| Backend | Python, FastAPI |
| Database | SQLite, SQLAlchemy |
| Authentication | JWT, bcrypt |
| Containerization | Docker |
| Testing | Pytest |
| Cloud target | AWS EC2, subject to eligibility and cost verification |
| Version control | Git, GitHub |

## Architecture

```text
Browser
   |
   v
React + TypeScript Dashboard
   |
   | Authenticated HTTP requests
   v
FastAPI REST API
   |
   +---- Authentication and authorization
   |
   +---- Project and ZIP upload management
   |
   +---- SQLite database
   |
   v
Docker Deployment Engine
   |
   +---- Build application image
   +---- Run container
   +---- Monitor status and logs
   +---- Stop / restart deployment
   |
   v
Deployed Application
```

## Project Structure

```text
CloudDeploy-Lite/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── sample-app/
├── docs/
├── .github/
│   └── workflows/
├── .env.example
├── .gitignore
└── README.md
```

## Prerequisites

Install the following before running the project:

- Python and pip
- Node.js and npm
- Docker Desktop with a running Docker Engine for real deployments
- Git

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/CloudDeploy-Lite.git
cd CloudDeploy-Lite
```

### 2. Start the backend

In a terminal:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Configure the required environment variables using `.env.example` as a reference. Do not commit real secrets.

Start the API:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend health check: `http://127.0.0.1:8000/health`

Interactive API documentation: `http://127.0.0.1:8000/docs`

### 3. Start the frontend

Open a second terminal:

```powershell
cd frontend
npm install
```

Configure the frontend environment in `frontend/.env`:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Start the development server:

```powershell
npm run dev
```

Open the local URL printed by Vite, typically `http://localhost:5173`.

Restart Vite after changing environment variables.

## Running Tests

### Backend

From the `backend` directory with its virtual environment activated:

```bash
pytest -q
```

### Frontend production build

From the `frontend` directory:

```bash
npm run build
```

A successful build verifies frontend compilation; it does not by itself verify the complete application workflow.

## Deployment Workflow

1. Register and log in.
2. Create a project.
3. Upload a ZIP containing the application source and a root-level `Dockerfile`.
4. Start a deployment.
5. Monitor its status and inspect logs.
6. Open the application URL when available.
7. Stop or restart the deployment as needed.

Real deployment requires a functioning Docker Engine. Use the trusted sample application for initial testing.

## Security Considerations

- Passwords are hashed rather than stored as plaintext.
- Protected API endpoints use JWT authentication and project ownership checks.
- ZIP uploads are validated and subject to configured limits.
- Container execution uses resource restrictions.
- Never commit `.env` files containing secrets, JWT signing keys, passwords, or credentials.
- This project is a learning MVP, not a hardened public multi-tenant hosting service. Arbitrary untrusted Docker builds require additional isolation and security review.

## Current Status

- Backend API and database foundation implemented.
- Authentication, project ownership, and ZIP upload validation implemented.
- Docker deployment engine and lifecycle controls implemented.
- React dashboard integrated with the backend.
- Backend tests reported: **40 passed, 1 skipped, 1 warning**.
- Frontend production build reported successful.
- Real Docker deployment remains to be verified in an environment with a running Docker daemon.
- AWS hosting is planned but has not yet been verified or deployed.

## Future Improvements

- Verify the complete deployment workflow using a running Docker Engine.
- Expand automated frontend and end-to-end testing.
- Benchmark API latency and deployment reliability under controlled workloads.
- Evaluate AWS hosting only after checking account eligibility, pricing, and security requirements.

## License

Choose a license before making this project open source. Until then, no license is specified.
