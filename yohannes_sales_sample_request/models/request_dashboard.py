from odoo import models, fields, api

class RequestDashboard(models.Model):
    _name = 'request.dashboard'
    _description = 'Request Dashboard Overview'
    
    name = fields.Char(string='Name', required=True)
    code = fields.Selection([
        ('free_sample', 'Free Sample Request'),
        ('return_sample_request', 'Return Sample Request'),
        ('sample_return', 'Sample Return'),
        ('consignment_issue', 'Consignment Issue'),
        ('consignment_receive', 'Consignment Receive')
    ], string='Type Code', required=True)
    color = fields.Integer(string='Color')
    
    count_draft = fields.Integer(compute='_compute_counts')
    count_to_approve = fields.Integer(compute='_compute_counts')
    count_approved = fields.Integer(compute='_compute_counts')

    def _compute_counts(self):
        for record in self:
            count_draft = 0
            count_to_approve = 0
            count_approved = 0
            
            if record.code == 'free_sample':
                count_draft = self.env['free.sample.request'].search_count([('state', '=', 'draft')])
                count_to_approve = self.env['free.sample.request'].search_count([('state', '=', 'Operations_store_manager')])
                count_approved = self.env['free.sample.request'].search_count([('state', '=', 'requested')])
                
            elif record.code == 'return_sample_request':
                count_draft = self.env['return.sample.request'].search_count([('state', '=', 'draft')])
                count_to_approve = self.env['return.sample.request'].search_count([('state', '=', 'Operations_store_manager')])
                count_approved = self.env['return.sample.request'].search_count([('state', '=', 'requested')])
                
            elif record.code == 'sample_return':
                count_draft = self.env['return.sample'].search_count([('state', '=', 'draft')])
                count_to_approve = self.env['return.sample'].search_count([('state', '=', 'Operations_store_manager')])
                count_approved = self.env['return.sample'].search_count([('state', '=', 'requested')])
                
            elif record.code == 'consignment_issue':
                count_draft = self.env['consignment.request'].search_count([('state', '=', 'draft')])
                count_to_approve = self.env['consignment.request'].search_count([('state', '=', 'Operations_store_manager')])
                count_approved = self.env['consignment.request'].search_count([('state', '=', 'requested')])
                
            elif record.code == 'consignment_receive':
                count_draft = self.env['consignment.return'].search_count([('state', '=', 'draft')])
                count_to_approve = self.env['consignment.return'].search_count([('state', '=', 'Operations_store_manager')])
                count_approved = self.env['consignment.return'].search_count([('state', '=', 'requested')])
                
            record.count_draft = count_draft
            record.count_to_approve = count_to_approve
            record.count_approved = count_approved

    def action_open_draft(self):
        return self._open_action_view('draft')

    def action_open_to_approve(self):
        return self._open_action_view('Operations_store_manager')

    def action_open_approved(self):
        return self._open_action_view('requested')

    def action_open_all(self):
        return self._open_action_view(False)

    def _open_action_view(self, state=False):
        self.ensure_one()
        model_map = {
            'free_sample': 'free.sample.request',
            'return_sample_request': 'return.sample.request',
            'sample_return': 'return.sample',
            'consignment_issue': 'consignment.request',
            'consignment_receive': 'consignment.return',
        }
        
        target_model = model_map.get(self.code)
        domain = []
        if state:
            domain = [('state', '=', state)]
            
        return {
            'name': self.name,
            'type': 'ir.actions.act_window',
            'res_model': target_model,
            'view_mode': 'list,form',
            'domain': domain,
        }
