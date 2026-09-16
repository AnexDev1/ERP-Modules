# Inventory Operations

This module extends the core inventory capabilities of Odoo to introduce specialized, secure, and multi-step operational workflows tailored for **Group (Pharma & Pharmacy)**. It replaces standard single-click Odoo actions with rigorous, controlled procedures for internal transfers and stock adjustments.

## 🚀 Key Functional Features

### 1. Controlled Store Transfer Requests (`inventory.transfer.custom`)
Standard Odoo allows direct internal transfers with little oversight. This module introduces a formal "Request" layer for moving stock between warehouses or branches.
* **Multi-Warehouse Routing:** A single request can gather items from *multiple* source warehouses. The system intelligently splits the request into separate picking orders per warehouse in the background.
* **Approval Workflow:** Transfers must go through a formal sequence: `Draft` ➔ `Store Manager Approval` ➔ `Requested` ➔ `Received`.
* **Stock Validations:** Users cannot request more stock than is physically available in the source warehouse. The system validates `qty_requested` against `qty_available` in real-time.

### 2. Enterprise Stock Adjustment Requests (`stock.adjustment.request`)
Inventory adjustments (write-offs, true-ups, reconciliation) are financially sensitive operations. This feature locks down Odoo's standard "Update Quantity" button, replacing it with an auditable request form.
* **Categorized Adjustments:** Users must declare the *Purpose* of the adjustment: Inventory Reconciliation, Entry Correction, or Damaged/Scrap.
* **Smart Loading:**
  * *Load Inventory*: Instantly pulls all current system quantities for a specific physical location, allowing users to simply type the "Counted" quantity they actually see on the shelf.
  * *Load from Reference*: Used for Entry Corrections. Pulls the exact products from a past Delivery/Receipt to authorize a reversal or correction.
* **Live Valuation Tracking:** As users input their counted quantities, the system instantly computes the `Difference Qty` and total **Valuation Change (Value Adjustment)** based on the standard cost of the product.
* **Dual-Tier Approval:** Major adjustments require `Manager Approval` and then `Finance Approval` before the actual stock is modified.
* **Automated Accounting Traceability:** Once Finance approves and the operation is processed, the system creates the necessary background stock moves and automatically links the resulting **Journal Entries** directly onto the request form for easy financial auditing.

---

## 🛠️ Technical Implementation Details

This section details the underlying Odoo 19 architecture driving the operations module.

### 1. Store Transfer Architecture
The `inventory.transfer.custom` model acts as a master document that spawns native `stock.picking` records via the `_create_stock_pickings` method.
* **Mapping:** It uses a `collections.defaultdict` to group lines by `source_warehouse_id`. 
* **Picking Generation:** For each unique warehouse, it dynamically looks up the native `int_type_id` (Internal Transfer Operation Type) for that specific warehouse before spawning the `stock.picking`.
* **Odoo 19 Move Flow:** Once the `stock.move` records are created, it programmatically pushes them through the reservation engine using `moves._action_confirm()` and `moves._action_assign()`.

### 2. Stock Adjustment Mechanics
The `stock.adjustment.request` bypasses Odoo's standard `stock.quant` direct write capabilities, enforcing a strict double-entry movement process via the `_create_inventory_adjustment` method.
* **Virtual Location Resolution:** It locates the active virtual `inventory` location (filtered by `company_id`) to use as the counterpart for the adjustment.
* **Directional Logic:** If `difference_qty` is positive (found stock), the move flow is `Virtual Inventory` ➔ `Physical Location`. If negative (lost stock), the flow is reversed: `Physical Location` ➔ `Virtual Inventory`.
* **Lot/Serial Enforcement:** When creating the underlying `stock.move.line`, it correctly passes the `lot_id` if specified on the request line, ensuring high-compliance traceability.
* **Financial Hook Binding:** After invoking `picking.button_validate()` via code, it captures the resulting `account_move_id` from the moves and mounts them onto the `journal_entry_ids` many2many field using Odoo 19's `Command.set()`.

### 3. Dynamic UI Quants Querying
The `stock.adjustment.request.line` leverages `@api.onchange` to provide lightning-fast, real-time feedback. 
* When a user selects a Product or a Lot, the `_onchange_product_id` fires a direct `stock.quant` ORM search scoped exactly to the chosen Location/Product/Lot combination to instantly populate the `system_qty`, reducing data entry errors.

---
*Eyu Devo*
