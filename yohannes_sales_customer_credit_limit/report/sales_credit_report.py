from odoo import models, fields, api
from odoo.exceptions import UserError

class SalesCreditReport(models.Model):
    _name = 'sales.credit.report'
    _description = 'Sales Credit Report'

    def _get_report_domain(self):
        domain = [('state', 'in', ['sale', 'done'])]  # Only confirmed sales orders
        if self.env.context.get('partner_id'):
            domain.append(('partner_id', '=', self.env.context.get('partner_id')))
        if self.env.context.get('date_from'):
            domain.append(('date_order', '>=', self.env.context.get('date_from')))
        if self.env.context.get('date_to'):
            domain.append(('date_order', '<=', self.env.context.get('date_to')))
        if self.env.context.get('sale_type'):
            domain.append(('sale_type', '=', self.env.context.get('sale_type')))
        return domain

    def action_print_report(self):
        domain = self._get_report_domain()
        data = {
            'domain': domain,
            'date_from': self.env.context.get('date_from'),
            'date_to': self.env.context.get('date_to'),
            'partner_id': self.env.context.get('partner_id'),
            'sale_type': self.env.context.get('sale_type'),
        }
        report = self.env.ref('yohannes_sales_customer_credit_limit.action_report_sales_credit', raise_if_not_found=False)
        if not report:
            raise UserError("The Sales Credit Report is not available.")
        return report.report_action(self, data=data)
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sale_type = fields.Selection([
        ('cash', 'Cash'),
        ('credit', 'Credit'),
    ], string='Sale Type', default='cash', help="Type of sale transaction")

    def action_print_report(self):
        # Proxy method to call the report from sales.credit.report
        report_model = self.env['sales.credit.report']
        return report_model.with_context(
            self._context
        ).action_print_report()