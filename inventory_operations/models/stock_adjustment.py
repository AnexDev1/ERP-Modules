from odoo import models, fields, api, Command, _
from odoo.exceptions import UserError, ValidationError


class DrogaStockAdjustmentRequest(models.Model):
    _name = 'stock.adjustment.request'
    _description = 'Enterprise Stock Adjustment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(default='New', copy=False, readonly=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('store_manager', 'Store Manager'),
        ('finance_approver', 'Finance Approver'),
        ('approved', 'Approved'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], default='draft', tracking=True)

    adjustment_purpose = fields.Selection([
        ('reconciliation', 'Inventory Reconciliation'),
        ('correction', 'Entry Correction'),
        ('scrap', 'Damaged/Scrap'),
    ], string='Purpose', default='reconciliation', required=True)

    reference_doc = fields.Many2one('stock.picking', 'To Correct Ref', check_company=True, help="Reference to the document being corrected")
    description = fields.Text('Adjustment Description')

    total_value_change = fields.Monetary(
        string='Total Value Adjustment',
        compute='_compute_total_value',
        currency_field='currency_id',
        store=True
    )
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        required=True,
    )

    location_id = fields.Many2one(
        'stock.location',
        required=True,
        domain="[('usage','=','internal')]",
    )

    line_ids = fields.One2many(
        'stock.adjustment.request.line',
        'adjustment_id',
        copy=True,
    )

    picking_id = fields.Many2one('stock.picking', readonly=True)
    journal_entry_ids = fields.Many2many('account.move', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'stock.adjustment.request'
                ) or 'New'
        return super().create(vals_list)

    @api.depends('line_ids.subtotal_value')
    def _compute_total_value(self):
        for rec in self:
            rec.total_value_change = sum(rec.line_ids.mapped('subtotal_value'))

    def action_submit(self):
        if not self.line_ids:
            raise UserError(_("Add at least one line."))
        self.write({'state': 'store_manager'})

    def action_manager_approve(self):
        self.write({'state': 'finance_approver'})

    def action_finance_approve(self):
        self.write({'state': 'approved'})

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_load_inventory(self):
        self.ensure_one()
        if not self.location_id:
            raise UserError(_("Please select a location first."))

        self.line_ids.unlink()

        quants = self.env['stock.quant'].search([
            ('location_id', '=', self.location_id.id),
            ('quantity', '>', 0) 
        ])

        new_lines = []
        for quant in quants:
            new_lines.append((0, 0, {
                'product_id': quant.product_id.id,
                'lot_id': quant.lot_id.id if quant.lot_id else False,
                'counted_qty': quant.quantity,
            }))

        if not new_lines:
            raise UserError(_("No stock found in this location."))

        self.write({'line_ids': new_lines})

    def action_load_from_reference(self):
        self.ensure_one()
        if not self.reference_doc:
            raise UserError(_("Please select a Reference Document first."))

        self.line_ids.unlink()

        new_lines = []
        for move in self.reference_doc.move_ids:
            new_lines.append((0, 0, {
                'product_id': move.product_id.id,
                'counted_qty': 0, 
            }))

        if not new_lines:
            raise UserError(_("No items found in the selected picking."))

        self.write({'line_ids': new_lines})

    def action_process(self):
        for rec in self:
            if rec.state != 'approved':
                raise UserError(_("Only approved adjustments can be processed."))

            picking = rec._create_inventory_adjustment()

            account_moves = picking.move_ids.account_move_id

            rec.write({
                'picking_id': picking.id,
                'journal_entry_ids': [Command.set(account_moves.ids)],
                'state': 'done'
            })

    def action_cancel(self):
        for rec in self:
            if rec.state == 'done':
                raise UserError(_("Cannot cancel a processed adjustment."))
        self.write({'state': 'cancel'})

    def action_view_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stock Move'),
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'view_mode': 'form',
        }

    def _create_inventory_adjustment(self):
        self.ensure_one()

        inventory_location = self.env['stock.location'].search([
            ('usage', '=', 'inventory'),
            '|', ('company_id', '=', self.company_id.id), ('company_id', '=', False)
        ], limit=1)

        if not inventory_location:
            raise UserError(_("No inventory adjustment location found. Please contact administrator."))

        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id.company_id', '=', self.company_id.id)
        ], limit=1)

        if not picking_type:
            raise UserError(_("No internal picking type found."))

        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': inventory_location.id,
            'location_dest_id': self.location_id.id,
            'origin': self.name,
            'company_id': self.company_id.id,
        })

        for line in self.line_ids:

            if line.difference_qty == 0:
                continue

            if line.difference_qty > 0:
                source = inventory_location
                dest = self.location_id
            else:
                source = self.location_id
                dest = inventory_location

            move = self.env['stock.move'].create({
                'description_picking': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom_qty': abs(line.difference_qty),
                'product_uom': line.product_id.uom_id.id,
                'picking_id': picking.id,
                'location_id': source.id,
                'location_dest_id': dest.id,
                'company_id': self.company_id.id,
            })

            move._action_confirm()
            move._action_assign()

            move_line_vals = {
                'move_id': move.id,
                'product_id': line.product_id.id,
                'product_uom_id': line.product_id.uom_id.id,
                'quantity': abs(line.difference_qty),
                'picked': True,
                'location_id': source.id,
                'location_dest_id': dest.id,
                'company_id': self.company_id.id,
            }

            if line.lot_id:
                move_line_vals['lot_id'] = line.lot_id.id

            self.env['stock.move.line'].create(move_line_vals)

        picking.button_validate()

        return picking


class DrogaStockAdjustmentRequestLine(models.Model):
    _name = 'stock.adjustment.request.line'
    _description = 'Adjustment Line'
    _check_company_auto = True

    adjustment_id = fields.Many2one(
        'stock.adjustment.request',
        required=True,
        ondelete='cascade',
    )

    company_id = fields.Many2one(
        related='adjustment_id.company_id',
        store=True,
    )

    product_id = fields.Many2one(
        'product.product',
        required=True,
        domain="[('is_storable','=',True)]",
    )

    lot_id = fields.Many2one(
        'stock.lot',
        domain="[('product_id','=',product_id)]",
    )

    counted_qty = fields.Float(required=True)

    system_qty = fields.Float(
        compute='_compute_system_qty',
        store=True,
    )

    difference_qty = fields.Float(
        compute='_compute_difference',
        store=True,
    )

    unit_cost = fields.Float(
        'Unit Cost',
        compute='_compute_system_qty', 
        store=True
    )

    subtotal_value = fields.Float(
        'Valuation Change',
        compute='_compute_valuation',
        store=True
    )

    @api.depends('product_id', 'adjustment_id.location_id', 'lot_id')
    def _compute_system_qty(self):
        for rec in self:
            domain = [
                ('product_id', '=', rec.product_id.id),
                ('location_id', '=', rec.adjustment_id.location_id.id),
            ]
            if rec.lot_id:
                domain.append(('lot_id', '=', rec.lot_id.id))

            quants = self.env['stock.quant'].search(domain)
            rec.system_qty = sum(quants.mapped('quantity'))
            rec.unit_cost = rec.product_id.standard_price

    @api.onchange('product_id', 'lot_id')
    def _onchange_product_id(self):
        """Provide instant feedback when picking a product or lot"""
        if self.product_id and self.adjustment_id.location_id:
            domain = [
                ('product_id', '=', self.product_id.id),
                ('location_id', '=', self.adjustment_id.location_id.id),
            ]
            if self.lot_id:
                domain.append(('lot_id', '=', self.lot_id.id))
            
            quants = self.env['stock.quant'].search(domain)
            self.system_qty = sum(quants.mapped('quantity'))
            self.counted_qty = self.system_qty 

    @api.depends('counted_qty', 'system_qty')
    def _compute_difference(self):
        for rec in self:
            rec.difference_qty = rec.counted_qty - rec.system_qty

    @api.depends('difference_qty', 'unit_cost')
    def _compute_valuation(self):
        for rec in self:
            rec.subtotal_value = rec.difference_qty * rec.unit_cost