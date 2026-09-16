# Inventory: Product Category Policies

This module extends the standard Odoo Product Category model to introduce critical business and pharmaceutical policies for **Group**. Instead of configuring rules on a product-by-product basis, this module centralizes control at the category level, enforcing standardization across the entire catalog.

## 🚀 Key Functional Features

### 1. Master Catalog Visibility Control
Pharmaceutical catalogs often contain thousands of deprecated, seasonal, or pending products. This module provides a simple master switch to control their visibility.
* **"Available in Master" Toggle:** A switch on the product category that instantly hides the entire category (and all products within it) from operational dropdowns across the system.
* **Clean Operational Views:** If a category is turned off, its products will no longer appear when a user is making a Sales Order. 
* **Backend Management Maintained:** While hidden from day-to-day transaction screens, the products remain fully visible and manageable in the main Inventory master lists for administrators.

### 2. Automated Sales Reservation Releases
In high-volume pharmaceutical sales, protecting stock from being indefinitely held by lingering draft quotations is critical.
* **Category-Specific Time Limits:** You can define a maximum **Reservation Period (in Hours)** directly on the product category (e.g., 24 hours for normal items, 4 hours for high-demand seasonal medicines).
* **Automated Expiration:** An intelligent background job continuously monitors Draft and Sent Sales Quotes. If a quote holds a product past its category's allowed reservation time, the system automatically cancels the quotation, immediately releasing the reserved stock back into the available pool for other salespeople to sell.

### 3. Batch Expiry Alert Thresholds
Different types of medical supplies have different usable shelf lives, meaning a "Near Expiry" warning needs to happen at different times.
* **Dynamic Warning Days:** You can define the **Batch Expiry Alert (Days)** on the category (e.g., alert 90 days before for tablets, but 30 days before for rapidly degrading lab reagents).
* **Cross-Module Integration:** This threshold dynamically feeds into the live dashboard badges (`Valid`, `Near`, `Expired`) introduced in the main `inventory` module, ensuring warehouse staff are warned exactly when they need to be.

---

## 🛠️ Technical Implementation Details

This section details the underlying Odoo 19 architecture driving the category policy module.

### 1. Deep Query Filtering (`_search` & `_name_search` Overrides)
To achieve the "Available in Master" functionality without breaking existing historical records, the module overrides core ORM search methods across three models: `product.category`, `product.template`, and `product.product`.
* **Selection Dropdown Filtering:** The `_name_search` method is tapped to ensure users typing into M2O (Many2One) relational fields cannot see disabled products.
* **Low-Level ORM Masking:** The `_search` method is also overridden, forcibly appending a `('available_in_master', '=', True)` domain to low-level database reads.
* **Contextual Bypassing:** To allow Inventory Managers to still see disabled products in the main menu, the module overrides the `ir.actions.act_window` XML definitions for the core product menus to inject `{'ignore_availability': 1}` into the context. The ORM overrides read this context and purposefully bypass the filter.
* **JS Crash Prevention (ID Lookup Bypass):** The `_search` override contains a safeguard (`is_id_search`) that parses the incoming domain leaf nodes. If the frontend is specifically querying a known `id` (e.g., rendering a historical invoice line), it permits the read to prevent `TypeError: Cannot read properties of undefined` UI crashes in Odoo's Javascript framework.

### 2. Reservation Cron Job Engine (`sale.order`)
The automated cancellation of expired reservations is handled by `cron_release_expired_reservations()` injected into the `sale.order` model.
* **Performance Scoping:** It queries exclusively for `('state', 'in', ['draft', 'sent'])` to minimize the dataset.
* **Line-Level Evaluation:** It iterates over the `order_line`, pulling the `reservation_period_hrs` from the `line.product_id.categ_id`. 
* **Action Trigger:** If `datetime.now()` exceeds `order.create_date + timedelta(hours=allowed_hrs)`, it executes `order.action_cancel()` and logs a tracked `message_post` onto the Chatter for clear auditing of why the quote was dropped.

---
*Eyu Devo*
