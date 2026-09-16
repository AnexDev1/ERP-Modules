from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    customer_type = fields.Selection([
        ('wholesale', 'Wholesale Customers'),
        ('retail', 'Retail Customers'),
    ], string='Customer Type', default='wholesale', required=True,
        help="Determines which price (Wholesale or Retail) is used on Sales Orders for this customer.")

    # Override standard VAT label
    vat = fields.Char(string='TIN Number')

    @api.depends('name')
    def _compute_display_name(self):
        super()._compute_display_name()
        for partner in self:
            if partner.name:
                partner.display_name = partner.name

    @api.constrains('vat')
    def _check_vat_length(self):
        for partner in self:
            if partner.vat:
                vat_clean = partner.vat.strip()
                if len(vat_clean) < 10:
                    raise ValidationError(_("TIN Number cannot be less than 10 characters."))
                
                if len(vat_clean) == 10:
                    if not vat_clean.isdigit():
                        raise ValidationError(_("A 10-character TIN Number must contain only numbers. (Characters are only allowed for lengths greater than 10)."))

                duplicate = self.env['res.partner'].search([
                    ('id', '!=', partner.id),
                    ('vat', '=ilike', vat_clean),
                    ('commercial_partner_id', '!=', partner.commercial_partner_id.id)
                ], limit=1)
                
                if duplicate:
                    raise ValidationError(_("A customer with this TIN Number already exists: %s") % duplicate.display_name)

    @api.onchange('vat')
    def _onchange_vat_warning(self):
        if self.vat:
            vat_clean = self.vat.strip()
            if len(vat_clean) > 10:
                return {
                    'warning': {
                        'title': _("TIN Number Warning"),
                        'message': _("The entered TIN Number is more than 10 characters long. Please verify if this is correct.")
                    }
                }

    @api.model
    def _search(self, domain, *args, **kwargs):
        from odoo.orm.domains import Domain
        domain = Domain(domain or [])
        
        # If searching by specific ID(s), don't strictly filter
        is_id_search = False
        for term in domain:
            if isinstance(term, (list, tuple)) and len(term) == 3 and term[0] == 'id':
                is_id_search = True
                break
            
        if not is_id_search:
            res_partner_search_mode = self.env.context.get('res_partner_search_mode')
            if res_partner_search_mode == 'customer':
                domain &= Domain(['|', ('customer_rank', '>', 0), ('supplier_rank', '=', 0)])
            elif res_partner_search_mode == 'supplier':
                domain &= Domain(['|', ('supplier_rank', '>', 0), ('customer_rank', '=', 0)])
                
        return super()._search(domain, *args, **kwargs)
