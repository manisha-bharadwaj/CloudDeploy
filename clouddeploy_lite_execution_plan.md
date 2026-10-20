# CloudDeploy Lite — Execution Plan

**Purpose:** Build the smallest working version of CloudDeploy Lite, in clear stages, with explicit stop points and a strict AWS cost boundary.

**MVP promise:** A user can sign in, create a project, upload a ZIP containing a trusted test web app, deploy it in a Docker container, see its status and basic logs, open its URL, and stop/restart it.

**Core rule:** Build and prove the complete flow locally first. Do not create AWS resources until the AWS eligibility and billing gate in Phase 7 has passed. If an AWS resource is not explicitly available within the account's free offer, stop the AWS deployment phase and keep the project local. Do not upgrade to a paid AWS plan to make a step work.

---

## 1. Fixed scope

### Build only these features

- Register and log in.
- Store users and projects in SQLite.
- Create and list projects belonging to the signed-in user.
- Upload one ZIP file containing a trusted, supported test app.
- Validate the ZIP before extracting it.
- Build a Docker image and start a container.
- Show deployment state: `Queued`, `Building`, `Running`, or `Failed`.
- Show basic build/runtime logs.
- Show a URL for the running test app.
- Stop and restart a deployment.
- Add automated backend tests and a basic CI workflow.

### Fixed stack

| Area | Choice |
|---|---|
| Frontend | React + TypeScript |
| Backend | Python + FastAPI |
| Database | SQLite |
| ORM | SQLAlchemy |
| Authentication | Password hashing + JWT |
| App packaging | Docker |
| Tests | Pytest |
| CI | GitHub Actions |
| Cloud, only after the gate | One eligible EC2 instance, if the account's Free plan explicitly allows it at no charge |

Use simple REST endpoints and a single backend process. Keep deployment execution simple and sequential for the MVP.

---

## 2. Explicit non-goals — do not build these

Do **not** add any of the following during this plan:

- Kubernetes, ECS, EKS, Fargate, or a cluster.
- Redis, Kafka, Celery, or a distributed job queue.
- Amazon RDS, PostgreSQL, S3, ECR, Lambda, API Gateway, CloudFront, Route 53, a load balancer, NAT Gateway, or other extra AWS services.
- Custom domains, HTTPS certificate automation, autoscaling, multi-region support, high availability, or multiple deployment hosts.
- GitHub repository integration, automatic Git pushes, buildpacks, multiple language runtimes, or a marketplace.
- Billing/subscriptions, teams/organizations, invitations, analytics dashboards, or advanced monitoring.
- Production-grade support for arbitrary public users' uploaded code.
- A complicated microservice architecture, a separate worker fleet, or a frontend redesign before the deployment flow works.
- A paid AWS plan upgrade, paid add-ons, Marketplace images, Savings Plans, Reserved Instances, or paid support.
- Any resource whose free eligibility or price you have not checked in the account and selected region.

If an idea is not required for the MVP promise above, put it in a `Later` list and do not implement it now.

---

## 3. Stop/go rules

A phase is complete only when its exit checks pass. Do not move forward just because the code compiles.

| Gate | GO only when… | STOP when… |
|---|---|---|
| Gate A — API | Auth, ownership checks, and project APIs pass tests. | Any user can access another user's project. |
| Gate B — ZIP safety | Invalid, oversized, and path-traversal ZIPs are rejected. | Archive extraction can write outside the project directory. |
| Gate C — Local deploy | A trusted sample app builds, runs, opens, logs, stops, and restarts locally. | Deployment needs a shell command built from untrusted input, privileged containers, or host Docker socket access inside the app container. |
| Gate D — Security | Only trusted test users/apps are allowed; containers have resource limits and no cloud credentials. | The app is being opened to arbitrary public uploads. |
| Gate E — Tests | Backend tests and a clean setup guide pass on a fresh local environment. | The only proof is a successful manual demo. |
| Gate F — AWS eligibility | The account is on the AWS **Free account plan**, and every proposed resource and usage is explicitly available within that plan's no-charge boundary. | The console requires a Paid plan, the resource is not eligible, cost/eligibility is unclear, or the free allowance cannot cover the intended usage. Do not create it. |
| Gate G — Cloud smoke test | The cloud-hosted MVP works, cost/usage is still within the permitted free offer, and teardown is verified. | Any unexpected charge, unexpected resource, exhausted credits, plan change, or unclear billing state occurs. Stop cloud work and remove resources where possible. |

**Important:** “Free Tier” does not mean every AWS resource is free in every account. Offers depend on account eligibility, plan, region, dates, and usage. Never assume an EC2 instance or its storage/networking is free based on an old tutorial.

---

## 4. Execution phases

## Phase 0 — Set up the repository

**Goal:** Create a clean project structure before writing features.

Suggested structure:

```text
clouddeploy-lite/
  backend/
    app/
      api/
      core/
      models/
      schemas/
      services/
      main.py
    tests/
    requirements.txt
  frontend/
  sample-app/
  docs/
  .github/workflows/
  README.md
```

Tasks:
1. Create a Git repository.
2. Add separate `backend`, `frontend`, and `sample-app` folders.
3. Add `.gitignore` for virtual environments, `.env`, SQLite databases, uploads, logs, build outputs, and secrets.
4. Add a short README with setup commands.
5. Pin direct Python dependencies once the environment is working.
6. Store secrets in environment variables; commit only an `.env.example` with placeholder values.

**Exit check:** A fresh clone can follow the README to start the empty FastAPI backend and React frontend.

**STOP HERE if:** the basic setup is unreliable. Do not start authentication or cloud work until local setup is repeatable.

## Phase 1 — Build the backend foundation

**Goal:** A running FastAPI app with database models and migrations/simple table creation suitable for the MVP.

Tasks:
1. Create the FastAPI application and health endpoint, e.g. `GET /health`.
2. Configure SQLite using SQLAlchemy.
3. Create `User`, `Project`, and `Deployment` models.
4. Add request/response schemas and consistent error responses.
5. Add configuration via environment variables.
6. Add basic request logging without logging passwords, JWTs, or secrets.

Minimum data fields:
- `User`: `id`, `email`, `password_hash`, `created_at`.
- `Project`: `id`, `owner_id`, `name`, `created_at`.
- `Deployment`: `id`, `project_id`, `status`, `container_id`, `app_port`, `app_url`, `created_at`, `updated_at`, `error_summary`.

**Exit check:** The API starts, connects to SQLite, and creates/read-tests the models.

**Do not:** add PostgreSQL, RDS, Redis, a queue, or multiple backend services.

## Phase 2 — Authentication and project ownership

**Goal:** Users can register and log in, and all project data is owner-scoped.

Tasks:
1. Implement `POST /auth/register`.
2. Implement `POST /auth/login`.
3. Hash passwords using a maintained password-hashing library; never store plaintext passwords.
4. Issue and verify JWTs using a secret provided through environment configuration.
5. Implement authenticated `POST /projects` and `GET /projects`.
6. Add `GET /projects/{project_id}` if needed by the UI.
7. Check project ownership in every endpoint that reads, changes, deploys, stops, restarts, or reads logs for a project.
8. Test invalid credentials, missing tokens, expired/invalid tokens, and cross-user access.

**Exit check:** Automated tests prove that User A cannot read or operate on User B's project.

**STOP HERE if:** any endpoint accepts a user ID from the request as proof of identity, passwords are not hashed, or ownership checks are missing.

## Phase 3 — Safe ZIP upload

**Goal:** Accept a small trusted test app archive without unsafe extraction.

Tasks:
1. Implement `POST /projects/{project_id}/upload`.
2. Set a conservative maximum upload size (start with 25 MB, configurable).
3. Allow only `.zip` files.
4. Inspect archive entries before extraction.
5. Reject absolute paths, `..` traversal, suspicious symlinks, excessive file counts, and archives whose expanded size exceeds a configured limit.
6. Extract into a unique directory under a fixed project workspace, never a path supplied directly by the user.
7. Require a `Dockerfile` for the first MVP. Do not attempt automatic language detection.
8. Keep uploaded source files outside the frontend's public directory.
9. Delete incomplete temporary uploads when validation fails.

**Exit check:** A valid sample ZIP uploads; malformed, oversized, and traversal test ZIPs are rejected and cannot write outside the workspace.

**Do not:** execute scripts during upload, trust filenames/paths, or build a Docker command by concatenating untrusted strings.

## Phase 4 — Local Docker deployment engine

**Goal:** Complete the most important feature on the developer's own computer before using AWS.

Tasks:
1. Install Docker locally and confirm it works.
2. Create a tiny `sample-app` with a `Dockerfile` and a simple HTTP health endpoint.
3. Implement a deployment service with separate functions for validation, image build, container start, health check, status update, log retrieval, stop, and restart.
4. Use the Docker SDK or safe argument-list subprocess calls; do not use a shell to interpolate user-controlled strings.
5. Generate an internal image/container name from a server-generated ID.
6. Run containers as non-root where practical, with no privileged mode, no host networking, and no Docker socket mounted into deployed containers.
7. Apply CPU, memory, process-count, disk/workspace, and startup-time limits where supported by the local Docker configuration.
8. Do not pass AWS credentials, backend secrets, or the host environment into deployed containers.
9. Save the deployment status and a short failure summary in SQLite.
10. Capture bounded logs; avoid storing unlimited output.
11. Start with a fixed safe port mapping strategy. Do not let uploaded apps choose arbitrary host ports.
12. Make the UI poll status rather than keeping one HTTP request open for the entire build.

**Exit check:** From the dashboard, a user can upload the sample app, click Deploy, see `Building` then `Running`, open the app URL, view logs, stop it, and restart it. A broken sample app ends in `Failed` with a useful error summary.

**STOP HERE if:** local deployment does not reliably work end-to-end. Do not use AWS to debug unfinished local code.

## Phase 5 — Minimal frontend

**Goal:** A usable interface, not a polished product.

Screens:
1. Register/login.
2. Project list and create-project form.
3. Project detail with ZIP upload.
4. Deployment status, app URL, and logs.
5. Stop/restart controls.

Tasks:
1. Build the smallest React + TypeScript UI for these screens.
2. Store authentication safely for the chosen MVP setup; do not put tokens or secrets in source code.
3. Show loading, empty, success, and failure states.
4. Poll deployment status at a modest interval while a deployment is active; stop polling when it reaches a terminal state.
5. Disable buttons when an operation is in progress.
6. Display only logs/status that the authenticated user is authorized to access.

**Exit check:** A user can complete the entire Phase 4 flow without manually calling API endpoints.

**Do not:** add charts, complex styling, drag-and-drop animations, themes, or extra dashboard pages.

## Phase 6 — Tests, security checks, and local release

**Goal:** Make the local MVP repeatable and safe enough for a controlled demo.

Minimum tests:
- Registration, login, password hashing, and invalid credentials.
- Missing/invalid JWT.
- Project CRUD and owner isolation.
- Valid ZIP, wrong file type, oversize upload, path traversal, and expanded-size limit.
- Build failure, container startup, health-check failure, logs, stop, and restart.
- Container resource settings and absence of cloud credentials.
- UI happy path and common error states.

Tasks:
1. Add Pytest tests for the backend and deployment service.
2. Mock Docker in ordinary unit tests; keep a small integration test that runs only when Docker is available.
3. Add GitHub Actions to install dependencies and run tests. Do not add paid CI services.
4. Write setup, test, and troubleshooting steps in README.
5. Run the full flow from a clean local setup.
6. Use only trusted sample applications and known test users.

**Exit check:** The documented local setup works from a clean clone, tests pass, and the end-to-end demo is repeatable.

**STOP HERE if:** tests fail, the upload safety checks fail, or container isolation is not understood. A working local MVP is already a valid milestone; AWS is optional.

## Phase 7 — AWS eligibility and zero-charge gate

**Goal:** Decide whether this account can host the MVP without crossing the user's cost boundary.

Before creating any AWS resource:

1. Sign in to AWS Billing and verify the actual account plan and eligibility. Do not assume this is a new account.
2. If eligible, select/remain on the **Free account plan**. Do not upgrade to a Paid account plan.
3. Read the current AWS Free Tier offer details for the account, region, and intended EC2 instance type.
4. Check whether EC2, the selected AMI, EBS root volume, public IPv4/networking, data transfer, and any required supporting resource are allowed and covered by the no-charge plan.
5. Set up available Free Tier usage visibility/alerts. Treat an alert as a warning, not as a guarantee that every possible charge is covered.
6. Decide the maximum resource size and maximum runtime before creating anything.
7. If any item is unavailable, not covered, or unclear, **STOP. Do not launch it.** Continue with local-only deployment and document the cloud phase as blocked by the free-tier constraint.

AWS references to check immediately before this gate:
- Free Tier overview: https://aws.amazon.com/free/
- Free Tier plans: https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html
- Track Free Tier usage: https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/tracking-free-tier-usage.html
- EC2 pricing: https://aws.amazon.com/ec2/pricing/
- Public IPv4 pricing context: https://docs.aws.amazon.com/vpc/latest/userguide/vpc-ip-addressing.html

**Important billing nuance:** AWS currently documents a Free account plan for eligible new customers that prevents charges unless the account is upgraded, but the plan has limits and a finite lifetime. AWS also documents charges for public IPv4 addresses. Your account's current plan and eligibility determine what can actually be used. Do not rely on credits as proof that a resource is “free forever.”

**Exit check:** A written checklist confirms every intended resource is permitted by the current Free plan and there is no need to upgrade. If this cannot be proven, the correct result is **NO AWS DEPLOYMENT**.

## Phase 8 — Optional single-instance cloud smoke test

**Only do this if Phase 7 passes completely.** This is a small educational demo, not a production deployment platform.

Tasks:
1. Use only the EC2 instance type and storage/networking explicitly permitted by the account's current free offer.
2. Use one instance only. Do not create a load balancer, NAT Gateway, database service, object storage bucket, container registry, or extra server.
3. Install Docker and run the API/frontend on that same instance, with the simplest deployment supported by the instance.
4. Keep the SQLite database and workspace on the instance's local persistent disk, and document that this is not highly available.
5. Restrict administrative access to your own IP where possible. Expose only the minimum ports needed for the demo.
6. Never expose Docker's remote API or mount the host Docker socket inside deployed app containers.
7. Keep AWS credentials out of app containers and uploads.
8. Use only trusted test apps. Do not invite public users to upload arbitrary code.
9. Test one deployment at a time; stop the sample container when finished.
10. Check Billing/Free Tier usage after the smoke test and record the resources created.

**Exit check:** A trusted test user can deploy the sample app, view status/logs, open the URL, stop/restart it, and the AWS console still shows the resource and usage within the allowed no-charge boundary.

**STOP immediately if:** a paid-plan upgrade is requested, the console warns of chargeable use, credits/allowances are exhausted, an unexpected resource appears, public access creates an unacceptable risk, or billing status is unclear. Do not continue troubleshooting by adding AWS services.

## Phase 9 — Teardown and final verification

Tasks:
1. Stop all test app containers.
2. Remove temporary test images/containers and uploaded test archives that are no longer needed.
3. If the cloud phase was used, stop/delete the EC2 instance and remove any related resources created for this test, according to the intended cleanup plan.
4. Check for remaining EBS volumes, snapshots, public IPv4 addresses, elastic IPs, security groups, and other resources. Do not assume stopping an instance removes all chargeable resources.
5. Check the Billing and Free Tier pages again.
6. Record what was tested, the known limitations, and whether the AWS portion was completed or deliberately skipped.

**Exit check:** No unwanted test resources remain, and the README accurately explains local operation, optional cloud setup, security limits, and teardown.

---

## 5. Strict AWS allowlist

This is a **conditional allowlist**, not a promise that each item is free for every account.

| Resource | Rule |
|---|---|
| One EC2 instance | Only if the current account's Free plan explicitly permits the selected type and use without charges. |
| EC2 root EBS volume | Only the minimum size explicitly covered by the current eligible offer. |
| Public IPv4 address | Check separately because AWS documents public IPv4 charges. If it is not covered by the account's no-charge plan, do not proceed with public cloud hosting. |
| Security group | Use the default/necessary networking configuration; do not add paid networking services. |
| IAM role/policy | Only minimum permissions required; no credentials in app containers. |
| AWS billing/free usage pages | Use them to verify eligibility and track usage. |

**Everything else is out of scope for AWS in this MVP.** In particular: no S3, ECR, RDS, load balancers, NAT Gateways, Route 53, CloudFront, ECS/EKS, Fargate, or paid marketplace products.

Do not treat AWS credits as a reason to expand scope. Do not upgrade plans to unlock a service.

---

## 6. Security rules that must not be skipped

This project runs uploaded code inside containers. Containers alone are not a guarantee that arbitrary untrusted code is safe.

- Keep the deployment feature limited to the owner and trusted test users.
- Do not launch a public service that accepts arbitrary strangers' ZIP uploads.
- Validate ZIP paths, file counts, archive size, and expanded size before extraction.
- Use server-generated directories, image names, and container IDs.
- Never build shell commands from user-provided strings.
- Do not run deployed containers in privileged mode.
- Do not mount `/var/run/docker.sock` into deployed containers.
- Do not pass cloud credentials, JWT signing keys, environment secrets, or host files into deployed containers.
- Apply CPU, memory, process, disk, and runtime limits where supported.
- Restrict exposed ports and administrative access.
- Enforce ownership checks on project, deployment, log, stop, and restart operations.
- Bound stored logs and clean temporary files.
- If proper isolation cannot be demonstrated, keep deployment local and trusted-only.

---

## 7. Final definition of done

The MVP is done when all required checks below pass:

- [ ] A user can register and log in.
- [ ] A user can create and list only their own projects.
- [ ] A valid trusted app ZIP uploads and is safely extracted.
- [ ] An invalid or maliciously structured ZIP is rejected.
- [ ] The app builds and runs in Docker.
- [ ] The dashboard shows deployment state and bounded logs.
- [ ] The user can open the app URL.
- [ ] Stop and restart work.
- [ ] Automated tests cover auth, ownership, ZIP safety, and deployment states.
- [ ] CI runs the test suite.
- [ ] README documents setup, testing, limitations, and cleanup.
- [ ] No deferred features were added.
- [ ] AWS was used only if the eligibility gate passed; otherwise, cloud deployment was deliberately skipped.
- [ ] If AWS was used, the account was not upgraded to a Paid plan and the final resource/usage check passed.

**The stopping point is the checklist above.** Once it passes, stop building. Do not add more features just to make the project look bigger. Record future ideas separately and implement them only in a later, explicitly approved phase.
