{
    'name': 'Account Withholding Tax',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Manage Withholding Tax on Payments',
    'author': 'eden',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_payment_register_views.xml',
        'views/account_payment_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
