#-*- coding: utf-8 -*-
from odoo import api, fields, models, _
from datetime import date, datetime, timedelta as td
from odoo.exceptions import UserError


class VaccinationGroupLine(models.Model):
    _name = 'vaccination.group.line'
    _description = "Vaccination Group Line"

    group_id = fields.Many2one('vaccination.group', 'Group')
    product_id = fields.Many2one('product.product', 'Product', required=True)
    date_due_day = fields.Integer('Days to add',help="Days to add for next date")


class VaccinationGroup(models.Model):
    _name = 'vaccination.group'
    _description = "Vaccination Group"

    name = fields.Char(string='Group Name', required=True)
    group_line_ids = fields.One2many('vaccination.group.line', 'group_id', string='Medicament line')


class PBVaccination(models.Model):
    _name = 'pb.vaccination'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'pb.hms.mixin']
    _description = "Vaccination"

    STATES = {'cancel': [('readonly', True)], 'done': [('readonly', True)]}

    name = fields.Char(size=256, string='Name', tracking=True)
    patient_id = fields.Many2one('hms.patient', string='Patient', required=True, tracking=True)
    product_id = fields.Many2one('product.product', 'Vaccination', required=True, 
        domain=[('hospital_product_type', '=', "vaccination")],
        help='Vaccine Name. Make sure that the vaccine (product) has all the'\
        ' proper information at product level. Information such as provider,'\
        ' supplier code, tracking number, etc.. This  information must always'\
        ' be present. If available, please copy / scan the vaccine leaflet'\
        ' and attach it to this record')
    tracking = fields.Selection(related='product_id.tracking', store=True)
    lot_id = fields.Many2one("stock.lot", string="Lot/Serial Number", domain="[('product_id','=',product_id)]")
    dose = fields.Integer(string='Dose #')
    observations = fields.Char(string='Observations')
    next_dose_date = fields.Datetime(string='Next Dose Date')
    due_date = fields.Date('Due Date')
    given_date = fields.Date('Given Date')
    batch_image = fields.Binary('Batch Photo')
    state = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('to_invoice', 'To Invoice'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='scheduled', tracking=True)
    invoice_id = fields.Many2one('account.move', string='Invoice', ondelete='cascade', copy=False)
    physician_id = fields.Many2one('hms.physician', ondelete='restrict', string='Physician', 
        index=True, tracking=True)
    move_id = fields.Many2one('stock.move', string='Stock Move')
    company_id = fields.Many2one('res.company', ondelete='restrict',
        string='Hospital', default=lambda self: self.env.company)
    appointment_id = fields.Many2one("hms.appointment", string="Appointment")

    @api.onchange('product_id')
    def onchange_product(self):
        if self.product_id:
            self.dose = self.product_id.vaccine_dose_number

    def action_done(self):
        if self.env.user.company_id.vaccination_invoicing:
            self.state = 'to_invoice'
        else:
            self.state = 'done'
        self.given_date = fields.Date.today()
        if not self.move_id:
            self.consume_vaccine()

    def action_cancel(self):
        self.state = 'cancel'

    def action_shedule(self):
        self.state = 'scheduled'

    def unlink(self):
        for rec in self:
            if rec.state not in ['cancel']:
                raise UserError(_('Record can be deleted only in Cancelled state.'))
        return super(PBVaccination, self).unlink()

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values['name'] = self.env['ir.sequence'].next_by_code('pb.vaccination') or 'New Vaccination'
        return super().create(vals_list)

    def action_create_invoice(self):
        product_id = self.product_id
        if not product_id:
            raise UserError(_("Please Set Product first."))
        product_data = [{'product_id': product_id}]
        inv_data = {
            'physician_id': self.physician_id and self.physician_id.id or False,
        }
        pb_context = {'commission_partner_ids':self.physician_id.partner_id.id}
        invoice = self.with_context(pb_context).pb_create_invoice(partner=self.patient_id.partner_id, patient=self.patient_id, product_data=product_data, inv_data=inv_data)
        self.invoice_id = invoice.id
        if self.state == 'to_invoice':
            self.state = 'done'

    def view_invoice(self):
        invoices = self.mapped('invoice_id')
        action = self.pb_action_view_invoice(invoices)
        return action

    def pb_get_consume_locations(self):
        if not self.company_id.pb_vaccination_usage_location_id:
            raise UserError(_('Please define a Vaccination location where the consumables will be used.'))
        if not self.company_id.pb_vaccination_stock_location_id:
            raise UserError(_('Please define a Vaccination location from where the consumables will be taken.'))

        dest_location_id  = self.company_id.pb_vaccination_usage_location_id.id
        source_location_id  = self.company_id.pb_vaccination_stock_location_id.id
        return source_location_id, dest_location_id

    def consume_vaccine(self):
        for rec in self:
            source_location_id, dest_location_id = rec.pb_get_consume_locations()
            move = self.consume_material(source_location_id, dest_location_id,
                {
                    'product': rec.product_id,
                    'lot_id': rec.lot_id and rec.lot_id.id or False,
                    'qty': 1,
                })
            move.vaccination_id = rec.id
            rec.move_id = move.id

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: