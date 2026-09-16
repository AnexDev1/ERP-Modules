{
    "name": "Inventory Customizations",
    "version": "19.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "Pharmaceutical Inventory Management",
    "description": """
        Comprehensive inventory customizations:
        - Warehouse types and Analytic integration
        - Pharmaceutical product master data
        - Traceability and Expiry validation
        - Custom naming conventions
        - AMC based replenishment
    """,
    "author": "Consulting",
    "depends": [
        'stock', 
        'product', 
        'account', 
        'stock_account',
        'analytic', 
        'product_expiry',
        'procurement_store_requisition',
        'inventory_operations',
        'inventory_product_category',
        'deltatech_stock_negative',
    ],
    "data": [
        'security/ir.model.access.csv',
        'security/inventory_security.xml',
        'data/ir_cron.xml',
        'views/res_users_views.xml',
        'views/inventory_warehouse_views.xml',
        'views/inventory_product_views.xml',
        'views/inventory_picking_views.xml',
        'views/stock_quant_views.xml',
        'views/menu_actions.xml',
    ],
    "installable": True,
    "application": False,
    "license": "OEEL-1",
}
