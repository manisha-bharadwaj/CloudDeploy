# CloudDeploy Lite --- Architecture Document

**Version:** 1.0\
**Scope:** Beginner-friendly MVP\
**Purpose:** Let a user upload a supported web application, deploy it in
a Docker container on AWS EC2, and view its status and logs.

------------------------------------------------------------------------

## 1. Product Summary

CloudDeploy Lite is a small self-service deployment platform. A user
signs in, uploads a ZIP archive containing a supported application,
clicks **Deploy**, and receives a URL for the running application. The
dashboard shows whether the deployment is building, running, or failed,
and provides basic logs and stop/restart controls.

The first version is intentionally small. It proves the complete
deployment flow before adding GitHub integration, advanced monitoring,
custom domains, Redis, Kubernetes, or other optional services.

## 2. MVP Features

1.  Register and log in.
2.  Create and view projects.
3.  Upload a ZIP archive containing a supported test application.
4.  Start a deployment with one button.
5.  Build and run the application using Docker.
6.  Show deployment status and build/runtime logs.
7.  Display a URL for the running application.
8.  Stop and restart a deployment.

**Not included in the first version:** GitHub OAuth/webhooks, custom
domains, automatic scaling, Kubernetes, Kafka, Redis, advanced
analytics, multi-region deployment, and support for arbitrary untrusted
code.

## 3. Selected Technology Stack

  -----------------------------------------------------------------------
  Area                    Technology              Responsibility
  ----------------------- ----------------------- -----------------------
  Frontend                React + TypeScript      Dashboard and user
                                                  interaction

  Backend API             Python + FastAPI        Authentication,
                                                  projects, deployment
                                                  requests and status

  Database                SQLite initially        Users, projects and
                                                  deployment metadata

  Data access             SQLAlchemy              Database queries and
                                                  models

  Authentication          JWT + password hashing  Protect API routes and
                                                  user accounts

  Deployment runtime      Docker                  Build and run each
                                                  supported application
                                                  in a container

  Cloud host              AWS EC2                 Runs CloudDeploy and
                                                  the initial deployment
                                                  containers

  Optional cloud storage, Amazon S3               Store uploaded source
  later phase                                     ZIPs

  Optional image          Amazon ECR              Store built Docker
  registry, later phase                           images

  Testing                 Pytest                  Backend tests

  CI                      GitHub Actions          Run tests on code
                                                  changes
  -----------------------------------------------------------------------

SQLite keeps the first implementation simple. PostgreSQL can replace it
when the MVP is working. S3 and ECR are optional extensions, not
prerequisites for the first end-to-end deployment.

## 4. High-Level Architecture

``` mermaid
flowchart TD
    U[Developer in Browser] --> UI[React + TypeScript Dashboard]
    UI -->|HTTPS REST API| API[FastAPI Backend]
    API --> AUTH[Authentication and Authorization]
    API --> DB[(SQLite Database)]
    API --> JOB[Deployment Worker]
    JOB --> ZIP[Validate and Extract ZIP]
    ZIP --> BUILD[Build Docker Image]
    BUILD --> DOCKER[Docker Engine on EC2]
    DOCKER --> APP[Deployed Application Container]
    APP --> URL[Application URL / Port]
    JOB --> LOGS[Build and Runtime Logs]
    LOGS --> DB
    JOB --> DB
    UI -->|Poll deployment status| API
```

### AWS extensions (after the local deployment flow works)

``` mermaid
flowchart LR
    API[FastAPI / Deployment Worker on EC2] --> S3[Amazon S3: Source ZIPs]
    JOB[Deployment Worker] --> ECR[Amazon ECR: Docker Images]
    ECR --> DOCKER[Docker runtime on EC2]
```

For the initial version, the app can store uploaded ZIPs temporarily on
the EC2 host and build images locally. S3 and ECR can be added later to
demonstrate AWS storage services.

## 5. End-to-End Deployment Flow

1.  The user registers or logs in.
2.  The user creates a project and uploads a ZIP file.
3.  FastAPI checks the user's identity, upload size, file type, and
    project ownership.
4.  FastAPI creates a deployment record with status `queued`.
5.  A deployment worker validates and extracts the archive into a
    dedicated working directory.
6.  The worker builds a Docker image using a supported Dockerfile or a
    clearly defined build template.
7.  The worker starts a container with a restricted set of resources and
    a non-conflicting host port.
8.  The worker performs a health check against the application.
9.  The deployment record is updated to `running` or `failed`.
10. The dashboard polls the API and displays status, logs, and the
    application URL.
11. The user can stop or restart the container from the dashboard.

## 6. Main Components

### Frontend

-   Login and registration pages.
-   Project list and create-project form.
-   ZIP upload and Deploy action.
-   Deployment status, logs, and application link.
-   Stop and restart controls.

### FastAPI backend

-   Validates requests and authenticates users.
-   Enforces project ownership on every project/deployment endpoint.
-   Stores project and deployment metadata.
-   Creates deployment jobs and exposes status/log endpoints.
-   Calls a separate deployment-worker module for Docker operations.

### Deployment worker

-   Processes one deployment at a time in the MVP.
-   Validates ZIP contents and prevents path traversal.
-   Builds and starts Docker containers.
-   Captures build output and runtime logs.
-   Performs health checks and records success/failure.
-   Stops or restarts containers when requested.

### Database

Suggested initial tables:

**users** - `id` - `email` (unique) - `password_hash` - `created_at`

**projects** - `id` - `owner_id` (foreign key to users) - `name` -
`created_at`

**deployments** - `id` - `project_id` (foreign key to projects) -
`version` - `status` (`queued`, `building`, `running`, `failed`,
`stopped`) - `container_id` (nullable) - `image_tag` (nullable) -
`application_port` (nullable) - `log_path` (nullable) - `error_message`
(nullable) - `created_at` - `finished_at` (nullable)

For a first pass, keep logs in per-deployment files on the server and
expose them through an authenticated API. Do not store unlimited log
text in the database.

## 7. Initial API Design

  --------------------------------------------------------------------------------------------
  Method                  Endpoint                                     Purpose
  ----------------------- -------------------------------------------- -----------------------
  `POST`                  `/api/auth/register`                         Create account

  `POST`                  `/api/auth/login`                            Obtain access token

  `GET`                   `/api/projects`                              List the current user's
                                                                       projects

  `POST`                  `/api/projects`                              Create a project

  `GET`                   `/api/projects/{project_id}`                 Get a project owned by
                                                                       the current user

  `POST`                  `/api/projects/{project_id}/deployments`     Upload source ZIP and
                                                                       start deployment

  `GET`                   `/api/deployments/{deployment_id}`           Get deployment status
                                                                       and URL

  `GET`                   `/api/deployments/{deployment_id}/logs`      Get recent logs

  `POST`                  `/api/deployments/{deployment_id}/stop`      Stop a running
                                                                       deployment

  `POST`                  `/api/deployments/{deployment_id}/restart`   Restart a stopped
                                                                       deployment
  --------------------------------------------------------------------------------------------

Every project/deployment endpoint must verify ownership. Return clear
validation errors and never expose another user's deployment details.

## 8. Suggested Repository Structure

``` text
clouddeploy-lite/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── api/
│   │   └── App.tsx
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/          # settings and security
│   │   ├── db/            # database setup
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic request/response schemas
│   │   ├── api/           # route handlers
│   │   ├── services/      # project and deployment logic
│   │   └── workers/       # Docker deployment operations
│   ├── tests/
│   └── requirements.txt
├── deploy/
│   ├── Dockerfile
│   └── nginx/             # optional reverse proxy configuration
├── docs/
│   └── architecture.md
├── .github/
│   └── workflows/
│       └── tests.yml
└── README.md
```

## 9. AWS Deployment Plan

### Initial AWS setup

-   Launch one appropriately sized EC2 instance.
-   Install Docker and the platform's runtime dependencies.
-   Configure a security group to expose only the required web/API ports
    and the selected demo application port range.
-   Run CloudDeploy on the instance.
-   Use an EC2 IAM instance role for AWS access when S3/ECR are added;
    do not hardcode access keys.
-   Keep secrets in environment configuration and never commit them to
    Git.

### S3 extension

-   Upload source ZIPs to a private bucket.
-   Use unique object keys and restrict bucket permissions.
-   Apply a lifecycle policy if temporary uploads should be deleted.

### ECR extension

-   Push built images to a private ECR repository.
-   Tag images with immutable deployment versions.
-   Pull the selected image when deploying or rolling back.

**Cost note:** Do not assume EC2, ECR, or S3 will always be free. Check
current account-specific Free Tier allowances and pricing. Stop or
delete resources that are no longer needed; stopping EC2 does not remove
charges for all associated resources.

## 10. Security Requirements

Running uploaded code is inherently risky. The first version should be
private or limited to trusted demo applications.

-   Never expose the Docker socket to uploaded application containers.
-   Do not run uploaded containers in privileged mode.
-   Run containers as non-root where possible.
-   Apply CPU, memory, process, upload-size, and execution-time limits.
-   Reject path traversal, archive bombs, symlinks escaping the
    extraction directory, and unexpected archive contents.
-   Never pass user input directly into a shell command; use safe
    argument lists and strict validation.
-   Do not pass AWS credentials or the EC2 instance role's permissions
    into deployed application containers.
-   Enforce authentication and project ownership for all operations.
-   Use least-privilege IAM permissions and keep the database/log
    directories private.
-   Avoid deploying arbitrary public users' code on a single EC2 host. A
    public multi-user platform requires stronger isolation than this
    MVP.

## 11. Testing Plan

1.  Unit-test registration, login, validation, and project ownership.
2.  Test that invalid ZIP files and oversized uploads are rejected.
3.  Test a successful deployment using a known, harmless sample app.
4.  Test a failed build and confirm the error appears in the dashboard.
5.  Test stop and restart operations.
6.  Test that one user cannot view or manage another user's projects.
7.  Test health-check failure and container cleanup.
8.  Perform a manual end-to-end test on EC2.

## 12. Build Order

1.  Create the repository and run a basic FastAPI health endpoint.
2.  Build the React dashboard shell.
3.  Add SQLite models and project CRUD.
4.  Add registration, login, JWT validation, and password hashing.
5.  Deploy one hard-coded sample app through Docker from the backend.
6.  Add ZIP upload validation and per-deployment working directories.
7.  Add deployment status and logs to the dashboard.
8.  Add application URLs, stop/restart, and health checks.
9.  Deploy CloudDeploy Lite to EC2.
10. Add S3 and ECR only after the end-to-end path works.
11. Add tests, README, architecture diagram, and a short demo.

## 13. MVP Completion Criteria

The MVP is complete when a trusted test user can log in, create a
project, upload a supported application, deploy it as a Docker container
on EC2, open its URL, view status/logs, and stop or restart it.
Deployment records must persist, failures must be visible, and users
must not be able to access each other's projects.

At that point, stop adding features and document the system. Add GitHub
integration, PostgreSQL, S3/ECR, and stronger isolation as separate
improvements.
