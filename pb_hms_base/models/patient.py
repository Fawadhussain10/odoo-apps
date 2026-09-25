# -*- coding: utf-8 -*-

from odoo import api, fields, models ,_
from odoo.exceptions import UserError,ValidationError
from datetime import datetime


class PBPatient(models.Model):
    _name = 'hms.patient'
    _description = 'Patient'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'pb.hms.mixin', 'pb.documnt.mixin']
    _inherits = {
        'res.partner': 'partner_id',
    }
    _rec_names_search = ['name', 'code']

    def _rec_count(self):
        Invoice = self.env['account.move']
        for rec in self:
            rec.invoice_count = Invoice.sudo().search_count([('partner_id','=',rec.partner_id.id)])

    partner_id = fields.Many2one('res.partner', required=True, ondelete='restrict',
        string='Related Partner', help='Partner-related data of the Patient')
    gov_code = fields.Char(string='Government Identity', copy=False, tracking=True)
    marital_status = fields.Selection([
        ('single', 'Single'), 
        ('married', 'Married')], string='Marital Status', default="single")
    spouse_name = fields.Char("Spouse's Name")
    spouse_edu = fields.Char("Spouse's Education")
    spouse_business = fields.Char("Spouse's Business")
    education = fields.Char("Patient Education")
    is_corpo_tieup = fields.Boolean(string='Corporate Tie-Up', 
        help="If not checked, these Corporate Tie-Up Group will not be visible at all.")
    corpo_company_id = fields.Many2one('res.partner', string='Corporate Company', 
        domain="[('is_company', '=', True),('customer_rank', '>', 0)]", ondelete='restrict')
    emp_code = fields.Char(string='Employee Code')
    user_id = fields.Many2one('res.users', string='Related User', ondelete='cascade', 
        help='User-related data of the patient')
    primary_physician_id = fields.Many2one('hms.physician', 'Primary Care Doctor')
    pb_tag_ids = fields.Many2many('hms.patient.tag', 'patient_tag_hms_rel', 'tag_id', 'patient_tag_id', string="HMS Tags")

    invoice_count = fields.Integer(compute='_rec_count', string='# Invoices')
    occupation = fields.Char("Occupation")
    religion = fields.Char("Religion")
    caste = fields.Char("Tribe")
    nationality_id = fields.Many2one("res.country", string="Nationality")
    passport = fields.Char("Passport Number")
    active = fields.Boolean(string="Active", default=True)

    def check_gov_code(self, gov_code):
        patient = self.search([('gov_code','=',gov_code)],limit=1)
        if patient:
            raise ValidationError(_('Patient already exists with Government Identity: %s.') % (gov_code))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code','/')=='/':
                vals['code'] = self.env['ir.sequence'].next_by_code('hms.patient') or ''
            company_id = vals.get('company_id')
            if company_id:
                company_id = self.env['res.company'].sudo().search([('id','=',company_id)], limit=1)
            else:
                company_id = self.env.user.company_id
            if company_id.unique_gov_code and vals.get('gov_code'):
                self.check_gov_code(vals.get('gov_code'))
            vals['customer_rank'] = True
        return super().create(vals_list)

    def write(self, values):
        company_id = self.sudo().company_id or self.env.user.sudo().company_id
        if company_id.unique_gov_code and values.get('gov_code'):
            self.check_gov_code(values.get('gov_code'))
        return super(PBPatient, self).write(values)

    def view_invoices(self):
        invoices = self.env['account.move'].search([('partner_id','=',self.partner_id.id)])
        action = self.with_context(pb_open_blank_list=True).pb_action_view_invoice(invoices)
        action['context'].update({
            'default_partner_id': self.partner_id.id,
            'default_patient_id': self.id,
        })
        return action

    @api.model
    def send_birthday_email(self): 
        wish_template_id = self.env.ref('pb_hms_base.email_template_birthday_wish', raise_if_not_found=False)
        user_cmp_template = self.env.user.company_id.birthday_mail_template_id
        today = datetime.now()
        today_month_day = '%-' + today.strftime('%m') + '-' + today.strftime('%d')
        patient_ids = self.search([('birthday', 'like', today_month_day)])
        for patient_id in patient_ids:
            if patient_id.email:
                wish_temp = patient_id.company_id.birthday_mail_template_id or user_cmp_template or wish_template_id
                wish_temp.sudo().send_mail(patient_id.id, force_send=True)

    def geo_localize(self):
        # partner_id delegation (_inherits) proxies fields like partner_latitude/
        # partner_longitude onto this model, but NOT methods - geo_localize()
        # itself must be called on the underlying res.partner directly.
        self.mapped('partner_id').geo_localize()

    @api.model
    def _cron_geo_localize_patients(self, batch_size=100):
        """Geocode any patient whose partner has a real address but hasn't been
        located yet (0,0 is base_geolocalize's "not yet geocoded" sentinel).
        Batched and rate-paced (one request/sec) to stay within the free
        OpenStreetMap Nominatim usage policy, so this is a cron, not a bulk
        one-shot call."""
        patients = self.search([
            ('partner_latitude', '=', 0.0), ('partner_longitude', '=', 0.0),
            ('street', '!=', False), ('city', '!=', False),
        ], limit=batch_size)
        if not patients:
            return
        import time
        for patient in patients:
            patient.partner_id.geo_localize()
            time.sleep(1)

    @api.onchange('phone')
    def _onchange_mobile_warning(self):
        if not self.phone:
            return
        mobile = self.phone
        message = ''
        domain = [('phone','=',self.phone)]
        if self._origin and self._origin.id:
            domain += [('id','!=',self._origin.id)]
        patients = self.sudo().search(domain)
        for patient in patients:
            message += _('\nThe Mobile number is already registered with another Patient: %s, Government Identity:%s, DOB: %s.') %(patient.name, patient.gov_code, patient.birthday)
        if message:
            message += _('\n\n Are you sure you want to create a new Patient?')
            return {
                'warning': {
                    'title': _("Warning for Mobile Dupication"),
                    'message': message,
                }
            }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: