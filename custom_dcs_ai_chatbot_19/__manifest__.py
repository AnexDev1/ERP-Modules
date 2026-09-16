{
    'name': 'DCS: AI Chatbot Assistant 19',
    'version': '19.0.1.0.0',
    'category': 'Tools',
    'summary': 'AI-powered chatbot widget connected to n8n DCS Business Intelligence Agent',
    'description': """
        Adds a floating AI chatbot to the Odoo backend that communicates
        with the DCS Odoo AI Assistant running on n8n. Users can ask
        business questions about sales, invoices, customers, projects,
        and accounting in natural language.
    """,
    'author': 'Eyu Devo',
    'depends': ['base', 'web'],
    'data': [
        'data/config.xml',
        'security/security.xml',

    ],
    'assets': {
        'web.assets_backend': [
            'custom_dcs_ai_chatbot_19/static/src/css/chatbot.scss',
            'custom_dcs_ai_chatbot_19/static/src/js/chatbot.js',
            'custom_dcs_ai_chatbot_19/static/src/xml/chatbot.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
