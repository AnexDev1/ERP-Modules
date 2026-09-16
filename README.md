# ERP Modules (Odoo 19 Custom Addons)

This repository contains custom Odoo 19 addons and an automated CI/CD deployment pipeline to the production VPS server.

---

## 🚀 Running Locally via Docker

### 1. Prerequisites
- Install **Docker Desktop** on Windows / Mac / Linux.
- Start Docker Desktop.

### 2. Start Odoo 19 and PostgreSQL
In the root of this project, run:
```bash
docker compose -f docker-compose.local.yml up -d
```

This will:
- Spin up a **PostgreSQL 16** database container.
- Build the **Odoo 19** image with necessary packages (`qifparse`).
- Mount all custom addons in this repo to `/mnt/extra-addons`.
- Expose the web interface at **http://localhost:8069**.

### 3. Stop Local Containers
```bash
docker compose -f docker-compose.local.yml down
```

---

## 🔄 CI/CD Automatic Deployment to VPS

When changes are pushed to the `main` branch, a GitHub Action (`.github/workflows/deploy.yml`) triggers automatically:
1. Connects to the VPS via SSH.
2. Pulls the latest commits into `/opt/odoo/instances/odoo19/addons`.
3. Automatically restarts the Odoo 19 container to reload Python code and views.

### Required GitHub Secrets
Under **Settings -> Secrets and variables -> Actions**, configure:
- `VPS_HOST`: `188.245.83.73`
- `VPS_USERNAME`: `root`
- `VPS_SSH_KEY`: The private SSH key for GitHub Actions.
