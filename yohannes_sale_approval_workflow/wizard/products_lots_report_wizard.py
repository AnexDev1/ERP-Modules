from odoo import models, fields, api

class ProductsLotsReportWizard(models.TransientModel):
    _name = 'products.lots.report.wizard'
    _description = 'Products Lots Report Wizard'

    price_type = fields.Selection([
        ('wholesale', 'Wholesale'),
        ('retail', 'Retail')
    ], string='Price Type', required=True, default='wholesale')

    def action_print_report(self):
        data = {
            'form': self.read()[0],
            'quant_ids': self.env.context.get('active_ids', [])
        }
        return self.env.ref('yohannes_sale_approval_workflow.action_report_products_lots').report_action(self, data=data)
