from odoo import models, api, fields, _


class ResPartner(models.Model):
    _inherit = "res.partner"

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    pdc_count = fields.Integer(compute='_compute_pdc_count', string='PDC Cheques')

    def _compute_pdc_count(self):
        Pdc = self.env['pdc.wizard']
        for partner in self:
            partner.pdc_count = Pdc.search_count(
                [('partner_id', 'child_of', partner.id)]) if partner.id else 0

    def action_open_pdc_cheques(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('pb_pdc.pb_pdc_payment_menu_action')
        action['domain'] = [('partner_id', 'child_of', self.id)]
        action['context'] = {'default_partner_id': self.id}
        return action
