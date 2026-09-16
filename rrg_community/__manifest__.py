{
    'name': 'RRG Community',
    'summary': 'Community replacements for RRG Studio property, meters, and store requisitions',
    'version': '19.0.1.1',
    'category': 'Real Estate',
    'license': 'LGPL-3',
    'depends': ['account', 'analytic', 'hr', 'product', 'purchase', 'sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/rrg_views.xml',
    ],
    'application': True,
    'installable': True,
}
