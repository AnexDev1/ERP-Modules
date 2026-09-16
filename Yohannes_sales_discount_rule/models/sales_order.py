from odoo import api, fields, models, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    amount_undiscounted = fields.Monetary(
        string='Undiscounted Amount',
        compute='_compute_amount_undiscounted',
        store=True,
        currency_field='currency_id',
        help="Total amount before any discounts are applied."
    )
    
    applied_discount_rule_id = fields.Many2one(
        'discount.per.customer.type', string='Applied Auto Discount Rule',
        readonly=True, copy=False)

    @api.depends('order_line.price_unit', 'order_line.product_uom_qty', 'order_line.product_id')
    def _compute_amount_undiscounted(self):
        for order in self:
            order.amount_undiscounted = sum(
                line.price_unit * line.product_uom_qty for line in order.order_line
            )

    def action_apply_discounts(self, approval_context=False):
        self.ensure_one()
        applicable_rules = {}  # key: (model, res_id), value: {'reference': str, 'percentage': float, 'lines': [line_ids]}

        # Compute DPA rule once, as it's order-level
        dpa_domain = [
            ('state', '=', 'approved'),
            ('from_amount', '<=', self.amount_undiscounted),
            '|', ('to_amount', '=', 0), ('to_amount', '>', self.amount_undiscounted),
            ('payment_term_id', 'in', (False, self.payment_term_id.id)),
            ('company_id', '=', self.company_id.id),
        ]
        dpa_rules = self.env['discount.per.sales.amount'].search(dpa_domain, order='percentage desc')

        for line in self.order_line.filtered(lambda l: l.product_id and not l.is_manual_discount):
            partner = self.partner_id
            product = line.product_id
            qty = line.product_uom_qty
            is_core = product.is_core_product
            # category_id = partner.category_id
            payment_term = self.payment_term_id
            company = self.company_id

            def matches_core(rule_core, product_is_core):
                if rule_core == 'all':
                    return True
                if rule_core == 'core_product':
                    return product_is_core
                if rule_core == 'non_core_product':
                    return not product_is_core
                return False

            # 1. Discount per Customer Tag (DPC)
            dpc_domain = [
                ('state', '=', 'approved'),
                ('category_id', 'in', partner.category_id.ids),
                ('company_id', '=', company.id),
            ]
            if product.categ_id:
                dpc_domain += [
                    '|',
                    ('product_category_id', 'child_of', product.categ_id.id),
                    ('product_category_id', '=', False),
                ]
            dpc_rule = self.env['discount.per.customer.type'].search(dpc_domain, order='percentage desc', limit=1)
            if dpc_rule and matches_core(dpc_rule.core, is_core):
                key = ('discount.per.customer.type', dpc_rule.id)
                if key not in applicable_rules:
                    applicable_rules[key] = {
                        'reference': dpc_rule.DPC_reference,
                        'percentage': dpc_rule.percentage,
                        'lines': [],
                    }
                applicable_rules[key]['lines'].append(line.id)

            # 2. Discount per Customer and Product (DPCP)
            dpcp_domain = [
                ('state', '=', 'approved'),
                ('partner_id', '=', partner.id),
                ('product_id', '=', product.id),
                ('company_id', '=', company.id),
                ('payment_term_id', 'in', (False, payment_term.id)),
            ]
            dpcp_rule = self.env['discount.per.customer.and.product'].search(dpcp_domain, order='percentage desc',
                                                                             limit=1)
            if dpcp_rule:
                key = ('discount.per.customer.and.product', dpcp_rule.id)
                if key not in applicable_rules:
                    applicable_rules[key] = {
                        'reference': dpcp_rule.DPCP_reference,
                        'percentage': dpcp_rule.percentage,
                        'lines': [],
                    }
                applicable_rules[key]['lines'].append(line.id)

            # 3. Discount per Quantity Order (DPQ)
            dpq_domain = [
                ('state', '=', 'approved'),
                # ('product_id', '=', product.id),  # uncomment if needed
                ('from_quantity', '<=', qty),
                '|', ('to_quantity', '=', 0), ('to_quantity', '>', qty),
                ('payment_term_id', 'in', (False, payment_term.id)),
                ('company_id', '=', company.id),
            ]
            dpq_rule = self.env['discount.per.quantity.order'].search(dpq_domain, order='percentage desc', limit=1)
            if dpq_rule and matches_core(dpq_rule.core, is_core):
                key = ('discount.per.quantity.order', dpq_rule.id)
                if key not in applicable_rules:
                    applicable_rules[key] = {
                        'reference': dpq_rule.DPQ_reference,
                        'percentage': dpq_rule.percentage,
                        'lines': [],
                    }
                applicable_rules[key]['lines'].append(line.id)

            # 4. Discount per Sales Amount (DPA)
            if dpa_rules and matches_core(dpa_rules.core, is_core):
                key = ('discount.per.sales.amount', dpa_rules.id)
                if key not in applicable_rules:
                    applicable_rules[key] = {
                        'reference': dpa_rules.DPA_reference,
                        'percentage': dpa_rules.percentage,
                        'lines': [],
                    }
                applicable_rules[key]['lines'].append(line.id)

        if not applicable_rules:
            return {}

        wizard = self.env['sale.discount.wizard'].create({'order_id': self.id})
        for key, data in applicable_rules.items():
            model, rid = key
            self.env['sale.discount.wizard.line'].create({
                'wizard_id': wizard.id,
                'rule_model': model,
                'rule_id': rid,
                'reference': data['reference'],
                'percentage': data['percentage'],
                'apply': True,
                'applicable_line_ids': [(6, 0, data['lines'])],
            })

        return {
            'name': 'Select Discounts to Apply',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'sale.discount.wizard',
            'res_id': wizard.id,
            'target': 'new',
            'context': {**self.env.context, 'approval_context': approval_context}
        }

    def action_submit_for_approval(self):
        # AUTO-TRIGGER WIZARD
        if not self.env.context.get('approval_from_wizard'):
            action = self.action_apply_discounts(approval_context='submit')
            if action: return action
        return super().action_submit_for_approval()

    def action_approve_price_change(self):
        # AUTO-TRIGGER WIZARD
        if not self.env.context.get('approval_from_wizard'):
            action = self.action_apply_discounts(approval_context='approve_price')
            if action: return action
        return super().action_approve_price_change()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_manual_discount = fields.Boolean(
        string='Manual Discount',
        default=False,
        help="If checked, discount is set manually and not auto-computed from rules."
    )
    is_rule_based_discount = fields.Boolean(
        string='Rule-Based Discount',
        default=False,
        help="If checked, the manual discount is based on selected rules."
    )

    discount_rule_display = fields.Char(
        string='Discount Rule',
        compute='_compute_discount_rule_display',
        store=True,
        readonly=True,
        help="Displays the reference(s) of the applied discount rule(s), e.g., 'DPC00004'."
    )

    @api.depends('is_manual_discount', 'discount', 'product_id', 'product_uom_qty', 'order_id.partner_id',
                 'order_id.amount_undiscounted', 'order_id.payment_term_id', 'order_id.company_id',
                 'order_id.partner_id.category_id', 'product_id.categ_id', 'product_id.is_core_product')
    def _compute_discount_rule_display(self):
        # This method triggers _compute_discount for dependencies
        self._compute_discount()

    def _compute_discount(self):
        super()._compute_discount()  # Keep standard pricelist discount computation if any

        for line in self:
            if line.is_manual_discount:
                if not line.is_rule_based_discount:
                    line.discount_rule_display = 'Manual'
                # Else, keep the existing display for rule-based
                continue
            else:
                line.discount_rule_display = False
                # No automatic rule application here; moved to wizard

            # Trigger price change approval if needed (placeholder)
            if line.discount != 0:
                # Implement approval logic, e.g., set a state or notify
                pass

    @api.onchange('is_manual_discount')
    def _onchange_is_manual_discount(self):
        if self.is_manual_discount:
            self.discount_rule_display = 'Manual'
            self.is_rule_based_discount = False
        else:
            self._compute_discount()

    @api.onchange('discount')
    def _onchange_discount(self):
        if self.discount != 0 and not self.is_manual_discount:
            self.is_manual_discount = True
            self.is_rule_based_discount = False
            self.discount_rule_display = 'Manual'

    #@api.depends('is_manual_discount','discount','product_id','product_uom_qty','order_id.partner_id',
     #      'order_id.amount_undiscounted','order_id.payment_term_id','order_id.company_id','order_id.partner_id.category_id','product_id.categ_id','product_id.is_core_product')

    #def _compute_discount_rule_display(self):
     #   # This method is a placeholder; actual computation happens in _compute_discount
      #  # We trigger it here to ensure storage and dependencies
       # self._compute_discount()

    #def _compute_discount(self):
     #   super()._compute_discount()  # Keep standard pricelist discount computation if any
#
 #       for line in self:
  #          if not line.product_id or not line.order_id.partner_id:
   #             line.discount_rule_display = False
    #            continue

     #       if line.is_manual_discount:
      #          # For manual, keep the user-set discount, set display to 'Manual'
       #         line.discount_rule_display = 'Manual'
                # Optionally, trigger approval if discount > 0
        #        continue

            # Collect applicable discounts
         #   total_discount = line.discount  # Start with any existing (e.g., from pricelist)
          #  rules_applied = []

           # partner = line.order_id.partner_id
          #  product = line.product_id
          #  qty = line.product_uom_qty
          #  order_undiscounted = line.order_id.amount_undiscounted
          #  payment_term = line.order_id.payment_term_id
          #  company = line.order_id.company_id
          #  is_core = product.is_core_product
          #  customer_type = partner.customer_type_id

           # def matches_core(rule_core, product_is_core):
           #     if rule_core == 'all':
           #         return True
           #     if rule_core == 'core_product':
           #         return product_is_core
           #     if rule_core == 'non_core_product':
           #         return not product_is_core
           #     return False

            # 1. Discount per Customer Type (DPC)
           # dpc_domain = [
           #     ('state', '=', 'approved'),
           #     ('customer_type', '=', customer_type.id if customer_type else False),
           #     ('company_id', '=', company.id),
           # ]
           # if product.categ_id:
            #    dpc_domain += [
             #       '|',
             #       ('product_category_id', 'child_of', product.categ_id.id),
             #       ('product_category_id', '=', False),
             #   ]
           # dpc_rule = self.env['discount.per.customer.type'].search(dpc_domain, order='percentage desc', limit=1)
           # if dpc_rule and matches_core(dpc_rule.core, is_core):
           #     total_discount += dpc_rule.percentage  # Positive for discount
           #     rules_applied.append(dpc_rule.DPC_reference)

            # 2. Discount per Customer and Product (DPCP)
           # dpcp_domain = [
            #    ('state', '=', 'approved'),
             #   ('partner_id', '=', partner.id),
              #  ('product_id', '=', product.id),
              #  ('company_id', '=', company.id),
              #  ('payment_term_id', 'in', (False, payment_term.id)),
            #]
            #dpcp_rule = self.env['discount.per.customer.and.product'].search(dpcp_domain, order='percentage desc',
                                                                             #limit=1)
            #if dpcp_rule:
             #   total_discount += dpcp_rule.percentage
              #  rules_applied.append(dpcp_rule.DPCP_reference)

            # 3. Discount per Quantity Order (DPQ)
           # dpq_domain = [
            #    ('state', '=', 'approved'),
            #    #('product_id', '=', product.id),
            #    ('from_quantity', '<=', qty),
            #    '|', ('to_quantity', '=', 0), ('to_quantity', '>', qty),
            #    ('payment_term_id', 'in', (False, payment_term.id)),
            #    ('company_id', '=', company.id),
            #]
            #dpq_rule = self.env['discount.per.quantity.order'].search(dpq_domain, order='percentage desc', limit=1)
            #if dpq_rule and matches_core(dpq_rule.core, is_core):
            #    total_discount += dpq_rule.percentage
            #    rules_applied.append(dpq_rule.DPQ_reference)

            # 4. Discount per Sales Amount (DPA) - uses undiscounted total to avoid loops
            #dpa_domain = [
             #   ('state', '=', 'approved'),
              #  ('from_amount', '<=', order_undiscounted),
              #  '|', ('to_amount', '=', 0), ('to_amount', '>', order_undiscounted),
              #  ('payment_term_id', 'in', (False, payment_term.id)),
              #  ('company_id', '=', company.id),
            #]
            #dpa_rule = self.env['discount.per.sales.amount'].search(dpa_domain, order='percentage desc', limit=1)
            #if dpa_rule and matches_core(dpa_rule.core, is_core):
             #   total_discount += dpa_rule.percentage
              #  rules_applied.append(dpa_rule.DPA_reference)

            # Apply total discount (clamp between -100% and 100% or as needed)
           # line.discount = max(-100.0, min(100.0, total_discount))

            # Set display
           # line.discount_rule_display = ', '.join(rules_applied) if rules_applied else False

            # Trigger price change approval if needed (placeholder)
            #if line.discount != 0:
             #   # Implement approval logic, e.g., set a state or notify
             #   pass

  #  @api.onchange('is_manual_discount')
  #  def _onchange_is_manual_discount(self):
  #      if self.is_manual_discount:
  #          self.discount_rule_display = 'Manual'
  #      else:
  #          self._compute_discount()

  #  @api.onchange('discount')
  #  def _onchange_discount(self):
  #      if self.discount != 0 and not self.is_manual_discount:
  #          self.is_manual_discount = True  # Auto-set to manual if user changes discount
  #          self.discount_rule_display = 'Manual'

# Add to views: in sale_order_line form/tree, add discount_rule_display and is_manual_discount
# For approval, you may need a separate model or workflow on sale.order/sale.order.line
