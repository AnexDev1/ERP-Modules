from odoo import fields, models


class MaterialPurchaseRequisition(models.Model):
    _name = 'material.purchase.requisition'
    _description = 'Store / Material Requisition'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(default='New', copy=False)
    request_date = fields.Date(default=fields.Date.context_today)
    employee_id = fields.Many2one('hr.employee')
    department_id = fields.Many2one('hr.department')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    reason = fields.Text()
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('done', 'Done'),
    ], default='draft', tracking=True)
    line_ids = fields.One2many('material.purchase.requisition.line', 'requisition_id')

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_draft(self):
        self.write({'state': 'draft'})


class MaterialPurchaseRequisitionLine(models.Model):
    _name = 'material.purchase.requisition.line'
    _description = 'Store Requisition Line'

    requisition_id = fields.Many2one(
        'material.purchase.requisition', required=True, ondelete='cascade',
    )
    product_id = fields.Many2one('product.product')
    description = fields.Char()
    qty = fields.Float(default=1.0)
    uom = fields.Char()
    requisition_type = fields.Selection([
        ('internal', 'Internal'),
        ('purchase', 'Purchase'),
    ], default='internal')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
    ], default='draft')
