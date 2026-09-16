{
    'name': 'Payroll',
    'summary': 'Community payroll compatible with restored Enterprise 19 data',
    'version': '19.0.1.3',
    'category': 'Human Resources/Payroll',
    'license': 'LGPL-3',
    'depends': ['hr', 'hr_holidays', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/payroll_views.xml',
    ],
    'application': True,
    'installable': True,
}
