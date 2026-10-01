# ERP Modules (Odoo 19 Custom Addons)

This repository contains custom Odoo 19 addons and an automated CI/CD deployment pipeline to the production VPS server.

---

## 📦 Custom Addons for `ease_backup` Database

The `ease_backup` database uses 30 custom and community modules to run seamlessly on Odoo 19 Community without Enterprise dependencies:

### 1. Core Payroll & HR Suite
- **`payroll`**: Custom community payroll replacement compatible with restored Enterprise 19 data. Features salary rule engines, payslips, batches, contracts, access groups (`Officer: Manage Payroll`, `Manager: Payroll Administrator`), status workflow (*Draft*, *Verify*, *Done*, *Paid*), and built-in audit reports.
- **`ease_visibility`**: Role and visibility control rules tailored for Ease Group operations.
- **`esr_fast_login`**: Performance and fast authentication customizations.

### 2. Accounting & Financial Management
- **`base_accounting_kit`**: Full accounting package for Odoo Community (P&L, Balance Sheet, Asset Management, Bank Statements, Financial Reports).
- **`base_account_budget`**: Budget management and budgetary positions tracking for community edition.

### 3. Modern User Interface (MuK Web Suite)
- **`muk_web_theme`**: Modern responsive theme and branding.
- **`muk_web_appsbar`**: Quick app drawer and launcher bar.
- **`muk_web_chatter`**: Enhanced chatter and communication interface.
- **`muk_web_colors`**: Customizable UI accent and status colors.
- **`muk_web_dialog`**: Improved modal dialogs and popups.
- **`muk_web_group`**: Group view UI enhancements.
- **`muk_web_refresh`**: Dynamic view refresh and auto-sync.

### 4. Enterprise Compatibility Stubs
These lightweight modules satisfy foreign key, view, and model dependencies inherited from Odoo Enterprise, allowing the database to operate stably on Community:
- **`web_gantt`**, **`web_grid`**, **`web_map`**, **`web_cohort`**: View engine fallbacks (redirected cleanly to standard list/form views).
- **`sale_enterprise`**, **`stock_enterprise`**: Sales and inventory enterprise view/reporting stubs.
- **`hr_work_entry_enterprise`**, **`hr_work_entry_holidays_enterprise`**, **`hr_gantt`**, **`hr_holidays_gantt`**: Work entry and leave gantt compatibility layers.
- **`contacts_enterprise`**, **`analytic_enterprise`**: Analytic and contact management extensions.
- **`currency_rate_live`**, **`iap_extract`**, **`product_barcodelookup`**, **`ai_auto_install`**: Service and utility stubs.
- **`spreadsheet_dashboard_purchase_stock`**, **`spreadsheet_dashboard_stock`**: Stock and purchase spreadsheet dashboards.

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
