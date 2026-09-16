{
    "name": "Procurement Reporting",
    "version": "1.0.0",
    "category": "Inventory/Procurement",
    "summary": "Consolidated reporting for all procurement modules",
    "author": "Antigravity",
    "depends": [
        "procurement_base",
        "procurement_local_purchase",
        "procurement_foreign_purchase",
        "procurement_foreign_operations",
        "procurement_store_requisition",
        "procurement_local_rfq",
        "accounting_procurement",
    ],
    "data": [
        "views/procurement_report_views.xml",
        "views/procurement_report_actions.xml",
        "views/procurement_report_menus.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
