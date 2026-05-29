# Context

You are a saas business and development expert with expertise in refactoring desktop applications to saas applications, you are also an expert in financial systems and business models for small to medium sized businesses in brazil.
The spec in the file "2026-05-23-finacialsim-design.md" has proven not to meet the project's requirements.

## Task

- [] Use the contents of the file "2026-05-23-finacialsim-design.md" to refactor the project from a desktop application to a saas application based on the analysis in the previous step and the following requirements:

### General Requirements

#### Architecture

Frontend
    ↓
API Gateway
    ↓
Auth Service
    ↓
Financial Service
    ↓
Pix Service
    ↓
Notification Service
    ↓
Queue Workers

#### Tech Stack

- FastAPI or similar Python web framework
- React or similar JS framework
- Postgres or similar SQL database
- Run in docker container

### Business Requirements

- Implement RBAC (admin, manager, user)
- Implement multi-tenancy
- Provision payment gateway integration using pix (scaffold only)
- The application should be accessible via a web browser.
- The application should be accessible via a mobile device.
- The application should be accessible via a tablet device.

Due to the token intensive nature of the task, first propose and agree on a multi step plan dividing the task into phases, each phase as a new markdown file.
Ask me more questions to better understand the issue.
