# -*- coding: utf-8 -*-
{
    'name': 'PEDS Fiscal Integration',
    'version': '19.0.1.0.2',
    'category': 'Accounting/Localizations',
    'summary': 'Integrates Odoo Invoicing with local PEDS Fiscal Printing API',
    'description': """
This module allows Odoo to print fiscal invoices directly to the PEDS Fiscal Printer Service running on the local client network.
    """,
    'depends': ['account', 'web', 'yohannes_sale_approval_workflow'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/account_move_views.xml',
        'wizard/peds_action_wizard_views.xml',
        'views/peds_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'peds_fiscal_integration/static/src/js/peds_print_action.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
