# CloudDeploy Lite --- Product Specification

**Document version:** 1.0\
**Product type:** Beginner-friendly, single-server deployment platform
MVP\
**Primary goal:** Let a trusted user upload a supported web application,
deploy it in Docker on AWS EC2, and open the running application from a
browser.\
**Cost constraint:** Design for AWS Free Tier / Free Plan eligibility
only. AWS free usage is account- and offer-dependent; this document does
not guarantee that every account or configuration will cost \$0.

------------------------------------------------------------------------

## 1. Product Overview

CloudDeploy Lite is a small web application inspired by services such as
Render. It gives a user a simple dashboard to upload a ZIP archive of a
supported web application, click **Deploy**, and see whether the
application starts successfully in a Docker container on an AWS EC2
instance.

The first release prioritizes one complete working path over a large
feature list. It is for personal learning and trusted demonstration
applications---not a public service that runs arbitrary users' code.

## 2. Problem Statement

Deploying a web application often requires manually preparing a server,
building a Docker image, starting a container, checking logs, and
keeping track of whether the application is working. CloudDeploy Lite
provides a small dashboard and backend that automate these steps for
supported test applications.

## 3. Target User

-   The student/developer building and demonstrating the project.
-   A small number of trusted testers using known sample applications.

**Out of scope:** Public multi-tenant hosting, arbitrary untrusted
uploads, high availability, large-scale traffic, and production hosting
for paying customers.

## 4. Product Goals

The MVP must let a user:

1.  Register and log in.
2.  Create and view projects.
3.  Upload a supported application ZIP.
4.  trigger a deployment with one button.
5.  View build/deployment status and logs.
6.  Open the deployed application using a URL.
7.  Stop and restart a deployment.

The MVP should run locally during development and be deployable to one
AWS EC2 instance for demonstration.

## 5. Non-Goals

Do not build these in the first release:

-   GitHub OAuth or automatic deployment on Git pushes.
-   Kubernetes, ECS, or multi-server orchestration.
-   Kafka, Redis, or a separate distributed queue.
-   Custom domains, automatic HTTPS for each user app, or autoscaling.
-   Paid AWS services such as a load balancer, NAT Gateway, managed
    Redis, or managed database.
-   Amazon S3 and Amazon ECR integrations in the initial version.
-   Advanced analytics, teams, billing, or complex RBAC.
-   Support for arbitrary languages/frameworks and arbitrary build
    commands.

These can be considered later if the core product works and the cost
plan is reviewed.

## 6. Technology Stack

  -----------------------------------------------------------------------
  Component               Choice                  Reason
  ----------------------- ----------------------- -----------------------
  Frontend                React + TypeScript      User dashboard

  Backend                 Python + FastAPI        REST APIs and
                                                  deployment logic

  Database                SQLite                  Simple persistent
                                                  metadata for a
                                                  single-server MVP

  ORM                     SQLAlchemy              Structured database
                                                  access

  Authentication          JWT + secure password   Login and protected
                          hashing                 endpoints

  Application runtime     Docker                  Builds and runs
                                                  supported applications
                                                  in containers

  Cloud host              One AWS EC2 instance    Hosts the platform and
                                                  demonstration
                                                  containers

  Tests                   Pytest                  Backend unit and
                                                  integration tests

  CI                      GitHub Actions          Runs tests on code
                                                  changes

  AWS storage services    None required initially Avoid extra services
                                                  and cost while
                                                  validating the MVP
  -----------------------------------------------------------------------

### Cost-first architecture decision

Run Docker image builds and application containers on the same EC2 host.
Keep uploaded ZIP files and image layers on that instance during the
MVP. This avoids making S3 or ECR a prerequisite. It also means storage
is limited by the instance's disk and must be cleaned up.

SQLite is appropriate only for this small, single-instance learning
project. If the product later needs multiple backend instances or more
concurrent users, reassess the database architecture.

## 7. Functional Requirements

### FR-1: Registration and login

-   A user can register with an email and password.
-   Passwords are stored as hashes, never as plain text.
-   A user can log in and receive a token.
-   Protected endpoints reject missing or invalid tokens.

### FR-2: Project management

-   A logged-in user can create a project with a name.
-   A user can list only their own projects.
-   A user can open a project to see its deployments.
-   Project identifiers must be validated on every request.

### FR-3: Upload source archive

-   A user can upload a ZIP file for a project.
-   The backend enforces a small configurable upload-size limit.
-   The backend accepts only the supported project format defined by the
    implementation.
-   Invalid, oversized, or malformed archives are rejected with a clear
    error.
-   Archive extraction must prevent path traversal and files escaping
    the deployment directory.

### FR-4: Start deployment

-   The user can click **Deploy** for a project.
-   The backend creates a deployment record and marks it `queued` or
    `building`.
-   A deployment worker builds a Docker image from an approved
    Dockerfile or a fixed supported template.
-   The worker starts a container on an available, allowed port.
-   The system performs a health check before reporting success.

### FR-5: Status and logs

-   The dashboard displays `queued`, `building`, `running`, `failed`, or
    `stopped`.
-   The user can view recent build and runtime logs for their own
    deployment.
-   Failures include a useful error summary without exposing secrets or
    internal credentials.

### FR-6: Application URL

-   A successful deployment displays a reachable URL or host-and-port
    address.
-   The first version may use an EC2 public address plus an allocated
    port.
-   Only the ports explicitly allowed by the server firewall/security
    group may be reachable.
-   Do not claim HTTPS or custom-domain support in the MVP.

### FR-7: Stop and restart

-   A user can stop a running deployment.
-   A user can restart a stopped deployment if its image and
    configuration remain available.
-   Operations update deployment status and report failures.
-   The backend must verify ownership before controlling a container.

## 8. User Journey

1.  User opens the CloudDeploy Lite dashboard.
2.  User registers or logs in.
3.  User creates a project.
4.  User uploads a ZIP archive of a supported, trusted sample
    application.
5.  User selects **Deploy**.
6.  The backend validates the upload and creates a deployment record.
7.  The worker builds the image and starts a container.
8.  The dashboard shows build output and current status.
9.  After the health check succeeds, the dashboard displays the
    application URL.
10. The user opens the URL, views logs, and can stop or restart the
    application.

## 9. Architecture

``` mermaid
flowchart TD
    USER[Developer Browser] --> UI[React + TypeScript Dashboard]
    UI -->|REST API| API[FastAPI Backend]
    API --> AUTH[JWT Authentication and Ownership Checks]
    API --> DB[(SQLite Database)]
    API --> WORKER[Deployment Worker]
    WORKER --> VALIDATE[Validate ZIP and Extract Safely]
    VALIDATE --> BUILD[Build Docker Image]
    BUILD --> DOCKER[Docker Engine on EC2]
    DOCKER --> APP[Application Container]
    APP --> URL[EC2 Public Address + Allowed Port]
    WORKER --> LOGS[Deployment Logs]
    LOGS --> DB
    WORKER --> DB
    UI -->|Poll status and logs| API
```

### Deployment components

-   **React:** Forms, project list, deploy button, status, logs, and
    URL.
-   **FastAPI:** Authentication, authorization, validation, project
    APIs, deployment APIs, and status retrieval.
-   **SQLite:** Users, projects, deployment records, and status
    metadata.
-   **Deployment worker:** Handles image build, container
    start/stop/restart, health checks, and log collection.
-   **Docker:** Runs each supported test application in a separate
    container.
-   **EC2:** Hosts the dashboard/API and the initial application
    containers on one server.

For the MVP, the worker can run as a background process or controlled
worker module. The API should not block a request until a full build
completes; it should return a deployment ID and let the dashboard poll
for progress.

## 10. Data Model

### `users`

-   `id`
-   `email` (unique)
-   `password_hash`
-   `created_at`

### `projects`

-   `id`
-   `owner_id` (foreign key to users)
-   `name`
-   `created_at`

### `deployments`

-   `id`
-   `project_id` (foreign key to projects)
-   `version`
-   `status`
-   `image_tag` (nullable)
-   `container_id` (nullable)
-   `application_port` (nullable)
-   `log_path` (nullable)
-   `error_message` (nullable)
-   `created_at`
-   `finished_at` (nullable)

Environment variables, rollback history, and advanced metrics are not
required for the first release.

## 11. Initial API Specification

  --------------------------------------------------------------------------------------------
  Method                  Endpoint                                     Description
  ----------------------- -------------------------------------------- -----------------------
  `POST`                  `/api/auth/register`                         Register a user

  `POST`                  `/api/auth/login`                            Log in and obtain a
                                                                       token

  `GET`                   `/api/projects`                              List the current user's
                                                                       projects

  `POST`                  `/api/projects`                              Create a project

  `GET`                   `/api/projects/{project_id}`                 Get a project the user
                                                                       owns

  `POST`                  `/api/projects/{project_id}/deployments`     Upload ZIP and queue
                                                                       deployment

  `GET`                   `/api/deployments/{deployment_id}`           Get status and
                                                                       application URL

  `GET`                   `/api/deployments/{deployment_id}/logs`      Get recent deployment
                                                                       logs

  `POST`                  `/api/deployments/{deployment_id}/stop`      Stop a deployment

  `POST`                  `/api/deployments/{deployment_id}/restart`   Restart a deployment
  --------------------------------------------------------------------------------------------

All project and deployment endpoints must enforce ownership. Never trust
a project or deployment ID supplied by the client without checking it
against the authenticated user.

## 12. AWS Free-Tier Cost Guardrails

The project must be designed around the lowest-complexity AWS setup, but
actual free eligibility depends on the AWS account, account plan,
region, instance type, and current offer terms.

### Required approach

-   Prefer the AWS **Free Plan** if the account is eligible and the
    available service options meet the project needs.
-   Before launching anything, verify EC2 eligibility, available
    instance types, storage allowances, account credits, and plan
    restrictions in the AWS console.
-   Use one small eligible EC2 instance only; do not create multiple
    servers.
-   Do not create a load balancer, NAT Gateway, EKS cluster, RDS
    database, ElastiCache instance, or other paid managed service for
    this MVP.
-   Keep the deployment count low and use tiny, trusted sample apps.
-   Configure upload limits, container CPU/memory limits, and disk
    cleanup.
-   Delete unused images, containers, archives, and volumes carefully.
-   Monitor the AWS Billing/Free Tier page and set available budget or
    usage alerts.
-   Stop the instance when it is not needed. Understand that stopping
    EC2 does not necessarily stop all charges for attached storage,
    public IPv4 addresses, snapshots, or other resources.
-   Delete resources no longer needed and verify that no chargeable
    resources remain.

### Important limitation

AWS changed its Free Tier account plans and offers. New accounts may be
offered a Free Plan with limited service access and a finite duration;
existing accounts can have different terms. Do not assume the legacy "12
months free" rules apply. See the official links in Section 16 before
provisioning resources.

**No-cost objective:** If the user needs a strict guarantee of no AWS
charges, develop and test locally first and do not provision AWS
resources unless their account plan explicitly prevents charges for the
selected use. A normal paid-plan account can incur charges beyond
applicable free offers or credits.

## 13. Security and Safety Requirements

Running uploaded code on the same host as the deployment platform is a
significant security risk. The initial product must be private and
restricted to trusted demo applications.

-   Never expose the Docker socket to application containers.
-   Never run application containers in privileged mode.
-   Run containers as non-root where practical.
-   Set CPU, memory, process-count, execution-time, and upload-size
    limits.
-   Reject unsafe ZIP paths, archive bombs, and symlinks that escape the
    extraction directory.
-   Do not construct shell commands by concatenating user input.
-   Do not pass AWS credentials or instance-role credentials into
    deployed application containers.
-   Use a least-privilege EC2 instance role only if AWS API access is
    needed.
-   Restrict security-group inbound ports to the minimum needed for the
    demo.
-   Keep SQLite, uploaded files, logs, and configuration files out of
    public web directories.
-   Never commit JWT secrets, passwords, private keys, or AWS
    credentials to Git.
-   Enforce authentication and project ownership for logs and all
    deployment operations.

Do not open the platform to arbitrary public uploads. A public hosting
service requires stronger isolation, quotas, abuse controls, and a more
robust multi-tenant architecture.

## 14. Non-Functional Requirements

-   **Reliability:** Failed builds should end in `failed`, not remain
    indefinitely `building`.
-   **Usability:** The dashboard should show a clear status and useful
    error messages.
-   **Security:** All project/deployment data must be protected by
    authentication and ownership checks.
-   **Maintainability:** Keep API routes, database models, business
    logic, and Docker operations in separate modules.
-   **Cost control:** Use one EC2 host, small trusted apps, upload
    limits, and cleanup procedures.
-   **Performance:** The API should return quickly after queueing a
    deployment; long builds run outside the request-response path.
-   **Observability:** Record timestamps, status changes, and build
    errors for each deployment.

## 15. Acceptance Criteria

The MVP is ready when all of these are true:

-   [ ] A user can register and log in.
-   [ ] A user can create and list their own projects.
-   [ ] A supported, trusted ZIP archive can be uploaded.
-   [ ] The deployment starts asynchronously and has a persistent status
    record.
-   [ ] Docker successfully builds and starts a known sample
    application.
-   [ ] The application can be opened through the displayed EC2 address
    and allowed port.
-   [ ] Build/runtime logs and failure summaries can be viewed by the
    project owner.
-   [ ] Stop and restart work for a deployment.
-   [ ] A user cannot access another user's project, deployment, or
    logs.
-   [ ] Upload validation and container limits are implemented.
-   [ ] The project has a README, setup instructions, and a working
    local development mode.
-   [ ] AWS resources and billing usage have been reviewed before and
    after the demo.

## 16. Development Milestones

1.  **Foundation:** Repository, FastAPI health endpoint, React shell,
    local setup.
2.  **Persistence:** SQLite models and project CRUD.
3.  **Authentication:** Registration, password hashing, JWT, ownership
    checks.
4.  **Single-app deployment:** Deploy a hard-coded trusted sample app
    using Docker.
5.  **ZIP deployment:** Add safe archive upload, validation, and
    deployment records.
6.  **Dashboard status/logs:** Show progress, errors, logs, and
    application URL.
7.  **Lifecycle controls:** Stop, restart, and health check.
8.  **AWS demo:** Deploy to one eligible EC2 instance after verifying
    the account's free plan and limits.
9.  **Hardening:** Tests, cleanup, resource limits, documentation, and
    demo video.

**Stop after Milestone 9.** Do not add optional services until the
acceptance criteria pass.

## 17. Official AWS References

Check current terms immediately before creating resources:

-   AWS Free Tier overview: https://aws.amazon.com/free/
-   AWS Free Tier account plans:
    https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html
-   Tracking Free Tier usage:
    https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/tracking-free-tier-usage.html
-   EC2 pricing: https://aws.amazon.com/ec2/pricing/
-   AWS billing and cost management:
    https://docs.aws.amazon.com/cost-management/

------------------------------------------------------------------------

## Final Product Definition

CloudDeploy Lite is complete when a trusted user can log in, upload a
supported web application, deploy it as a Docker container on one EC2
host, open the application URL, view deployment status and logs, and
stop or restart the deployment---all without requiring paid managed
services or optional AWS integrations.

The architecture is intentionally small. Its main engineering value is
the end-to-end deployment workflow, API and database design, Docker
integration, safe input handling, status tracking, and cloud deployment.
