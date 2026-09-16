{
    'name': 'Restored Data Visibility',
    'summary': 'Show restored confirmed orders, done transfers, and journal entries on Community',
    'version': '19.0.1.5',
    'license': 'LGPL-3',
    'depends': ['sale', 'purchase', 'stock', 'account', 'payroll', 'hr_work_entry_enterprise'],
    'data': [
        'data/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ease_visibility/static/src/js/enterprise_view_aliases.js',
        ],
        'web.assets_web': [
            'ease_visibility/static/src/js/enterprise_view_aliases.js',
        ],
    },
    'installable': True,
    'application': False,
}
