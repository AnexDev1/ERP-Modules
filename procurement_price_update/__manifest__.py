# -*- coding: utf-8 -*-
{
    'name': 'Procurement Price Update',
    'version': '19.0.1.0.0',
    'summary': 'Margin-based selling price update for local and foreign procurements.',
    'description': """
        This module allows procurement managers to define margins on products
        from purchase orders or stock receipts and update selling prices (list_price) accordingly.
    """,
    'category': 'Inventory/Purchase',
    'author': 'Droga Code',
    'depends': [
        'base',
        'purchase',
        'stock',
        'procurement_base',
        'procurement_local_purchase',
        'procurement_foreign_purchase',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
