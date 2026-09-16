# -*- coding: utf-8 -*-
{
    'name': 'Direct Attachment Print',
    'version': '19.0.1.0.0',
    'category': 'Tools',
    'summary': 'Directly print any attachment or document to local/USB printer',
    'description': """
Direct Attachment Print Module
==============================
Provides instant printing capabilities for any uploaded attachment, PDF, or document image in Odoo.
- Adds 'Print Attachment' action menu item to Document Attachments.
- Renames native Odoo Print button to 'Print Attachment' on Customer Invoices & Vendor Bills.
- Supports single or batch printing of attachments directly to default local/USB printers.
    """,
    'author': 'Yohannes ERP',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'account'],
    'data': [
        'views/ir_attachment_views.xml',
        'views/account_move_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'yohannes_direct_print/static/src/js/direct_print_action.js',
        ],
    },
    'installable': True,
    'application': False,
}
