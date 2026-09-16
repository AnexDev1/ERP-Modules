# -*- coding: utf-8 -*-
{
    'name': 'Landed Cost Retroactive Adjustment',
    'version': '19.0.1.0.0',
    'summary': 'Post additional stock valuations and COGS adjustments from landed costs within an open fiscal year.',
    'description': """
        When landed costs are discovered after a receipt has been validated,
        this module allows accountants to:

        1. Post an ADDITIONAL stock valuation journal entry for the receipt
           (DR Stock Valuation / CR Stock Variation) — without altering the
           original posted entries.

        2. Post a COGS adjustment entry for ALL deliveries of those products
           in the current fiscal year across all receipts/batches
           (DR COGS / CR Stock Valuation).

        The feature is only available while the fiscal year is still open.
    """,
    'category': 'Accounting/Inventory',
    'author': 'Droga Code',
    'depends': [
        'account',
        'stock_account',
        'stock',
        'inventory_accounting',
        'om_fiscal_year',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/landed_cost_adjustment_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
