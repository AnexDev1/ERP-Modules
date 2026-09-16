{
    'name': 'Yohannes Sales Report Customization',
    'version': '19.0.1.0.0',
    'category': 'Sales',
    'summary': 'Customizes the Sale Order/Pro-Forma invoice printout',
    'description': """
        This module customizes the sale report to:
        - Show actual Tax Names instead of Tax Labels
        - Add Total Amount in Words
        - Add a Company Stamp/Signature at the bottom of the invoice
    """,
    'depends': ['sale', 'account', 'yohannes_sale_approval_workflow', 'base_accounting_kit', 'Yohannes_sales_person_target_management', 'Yohannes_sales_credit_cash'],
    'data': [
        'views/res_company_views.xml',
        'views/sale_order_action_overrides.xml',
        'views/my_invoices_views.xml',
        'views/sale_report_templates.xml',
        'views/invoice_report_templates.xml',
        'views/delivery_report_templates.xml',
        'views/scrap_report_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
