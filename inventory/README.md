# Inventory Management

This module serves as the core inventory engine for **Pharma (HQ)** and **Pharmacy (Retail)**. It transforms standard inventory tracking into a highly automated, pharmaceutical-grade stock management system.

## 🚀 Key Functional Features

### 1. Smart Product Divisions
Products are no longer just generic items; they are assigned to specific operational divisions (**Import, Wholesale, Export, Pharmacy, or Manufacturing**). 
* **What this does:** The system intelligentally filters which warehouses a product can be stored in based on its division, preventing items from being received into incorrect locations.

### 2. Pharmaceutical Master Data
The system introduces specialized medical tracking directly on the product card:
* **Medical Details:** Track Manufacturer, Origin Country, and Active Ingredients (General Name).
* **Storage Compliance:** Assign temperature requirements like **Ambient (15-25°C)**, **Cold Chain (2-8°C)**, or **Narcotic/Controlled**.

### 3. Automated Replenishment & AMC Engine
The days of manually guessing how much stock to order are over. This module features a self-correcting replenish system.
* **Average Monthly Consumption (AMC):** A nightly automatic job analyzes the past 12 months of outward stock movements to calculate exactly how much of a product you sell/consume per month.
* **Dynamic Safety Stocks:** You define coverage targets (e.g., "Alert me at 4 months of stock, fill up to 6 months"). The system uses the AMC data to automatically update the Min/Max Reordering Rules for every single product across your warehouses.
* **Real-time Status Badges:** Instantly see if a product is **Healthy**, **Overstock**, or **Understock** just by looking at its card.

### 4. Expiry & Batch Safeguards
Strict compliance is enforced to prevent expired medicine distribution.
* **Live Expiry Dashboards:** Products display their real-time shelf-life status (**Valid, Near Expiry, or Expired**) based on the batch numbers currently sitting in your warehouse.
* **Configurable Alerts:** Define exactly how many days out you want to be warned (e.g., 90 days) before a batch expires.

### 5. "Zero-Touch" Procurement Routing
The system proactively ensures you never run out of stock.
* **Understock Warnings:** When stock dips below your emergency point, the Warehouse Manager gets an automated To-Do task alerting them to the issue.
* **Auto-Generating RFQs:** Based on your configured "Sourcing Strategy" (Local Only, Foreign Only, or Both), the system will seamlessly calculate the shortage and automatically generate a **Draft Purchase Requisition** directly in the Local or Foreign procurement departments. It even attaches the correct Company Budget Line automatically!

---

## 🛠️ Technical Implementation Details

This section is intended for Odoo Developers and Technical Maintainers working on the `inventory` module.

### 1. Multi-Company Data Architecture (`company_dependent=True`)
To allow a single Product ID to be shared across HQ and Pharmacy Branches, operational fields like **Average Monthly Consumption (`avg_monthly_consumption`)**, **Emergency Targets**, and **Sourcing Strategy** use Odoo's `company_dependent=True` property fields. 
* This relies on `ir.property` tables under the hood. 
* Background cron jobs use `self.with_company(company)` scoping to ensure calculations run in the correct context for each active division.

### 2. The AMC Calculation Engine (`stock.move` Aggregation)
The Average Monthly Consumption is not a stored field updated via triggers. Instead, a cron task (`cron_recompute_amc`) calculates it dynamically:
* Uses optimized `_read_group` queries on `stock.move`.
* Filters for moves in a `done` state within the last `relativedelta(years=1)`.
* Specifically defines "Consumption" as moves leaving an internal `usage` location of the current company to an external or cross-company destination.

### 3. Dynamic Reordering Rules Generation (`stock.warehouse.orderpoint`)
Instead of users manually configuring `stock.warehouse.orderpoint` records:
* The `cron_update_reordering_rules` loops over products and executes `action_update_reordering_rules()`.
* It calculates the required `min_qty` and `max_qty` based on the AMC and safety targets.
* It either updates the existing `orderpoint` or uses `.create()` to dynamically install a new auto-replenishment rule in the default warehouse.

### 4. Searchable Computed Fields & Context Bypass
The `stock_status` and `expiry_status` fields are computed dynamically for real-time dashboard badges without bloating the database tables (`store=False`).
* To maintain list view filtering capabilities on the UI, custom search fallback overrides (`_search_stock_status`, `_search_expiry_status`) map the filter request back to a domain query on `self.search([]).filtered(...) -> [('id', 'in', recs.ids)]`.

### 5. Automated Procurement Triggers & Mail Activities
When the system detects understock, it programmatically interfaces with cross-modular models safely:
* **Mail Activities:** Uses `self.activity_schedule` mapped to the `stock.group_stock_manager` role.
* **Requisition Injection:** Uses dynamic module checks (`if 'droga.local.purchase.requisition' in self.env`) to safely initiate `droga.local.purchase.requisition` or `droga.foreign.purchase.requisition` records, ensuring hard crashes do not happen if those custom modules are removed or uninstalled.
* **Validation Hook Constraints:** The core `button_validate` inside `stock.picking` is overloaded (`super`) to perform mandatory `lot_id` and `expiration_date` checking before Odoo processes stock moves, aggressively blocking invalid batch receipts.

---
*Eyu Devo*
