from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = 'res.partner'

    customer_credit_id = fields.One2many('customer.credit', 'partner_id', string="Customer Credit")
    yohannes_credit_limit = fields.Monetary(string="Credit Limit", related='customer_credit_id.maximum_credit', readonly=True)
    credit_payment_ids = fields.One2many('credit.payment', 'partner_id', string="Credit Payments")



    def action_view_customer_credit(self):
        self.ensure_one()
        action = self.env.ref('yohannes_sales_customer_credit_limit.action_customer_credit').read()[0]
        credit_ids = self.env['customer.credit'].search([('partner_id', '=', self.id)]).ids
        if len(credit_ids) == 1:
            action['views'] = [(self.env.ref('yohannes_sales_customer_credit_limit.view_customer_credit_form').id, 'form')]
            action['res_id'] = credit_ids[0]
        else:
            action['domain'] = [('id', 'in', credit_ids)]
        return action
    