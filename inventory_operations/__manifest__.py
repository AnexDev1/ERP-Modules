{
    "name": "Inventory Operations",
    "version": "19.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "Custom Operations for Group",
    "description": """
        Customization for Inventory Operations:
        - Requisition workflow (Draft, Store Manager, Requested, Received)
        - MTR Sequence generation
        - Source warehouse availability check
        - Stock Adjustment Request with approval workflow
    """,
    "author": "Eyu Devo",
    "depends": ['stock', 'account'],
    "data": [
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'data/inventory_transfer_sequence.xml',
        'data/stock_adjustment_sequence.xml',
        'views/inventory_transfer_views.xml',
        'views/stock_adjustment_views.xml',
        'views/stock_warehouse_views.xml',
        'views/inventory_transfer_menu_actions.xml',
    ],
    "installable": True,
    "application": False,
    "license": "OEEL-1",
}
