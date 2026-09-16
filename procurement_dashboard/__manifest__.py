{
    'name': 'Procurement Dashboard',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Procurement',
    'summary': 'Interactive analytics and management dashboard for local and foreign procurement',
    'description': """
        Provides a comprehensive dashboard summarizing:
        - Local & Foreign Purchase Requisitions (by state, amount)
        - RFQs / Comparison Sheets status
        - Purchase Orders metrics & spending
        - Shortage alerts (Store Requisitions)
    """,
    'author': 'Consulting',
    'depends': [
        'procurement_base',
        'procurement_store_requisition',
        'procurement_local_purchase',
        'procurement_foreign_purchase',
        'procurement_local_rfq',
        'procurement_foreign_rfq',
    ],
    'data': [
        'views/procurement_dashboard_actions.xml',
        'views/procurement_dashboard_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'procurement_dashboard/static/src/scss/procurement_dashboard.scss',
            'procurement_dashboard/static/src/js/procurement_dashboard.js',
            'procurement_dashboard/static/src/xml/procurement_dashboard.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
