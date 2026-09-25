# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PhysicianSpecialty(models.Model):
    _name = 'physician.specialty'
    _description = "Physician Specialty"

    code = fields.Char(string='Code')
    name = fields.Char(string='Specialty', required=True, translate=True)

    _name_uniq = models.Constraint('UNIQUE(name)', 'Name must be unique!')


class PhysicianDegree(models.Model):
    _name = 'physician.degree'
    _description = "Physician Degree"

    name = fields.Char(string='Degree')

    _name_uniq = models.Constraint('UNIQUE(name)', 'Name must be unique!')


class Physician(models.Model):
    _name = 'hms.physician'
    _description = "Physician"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _inherits = {'res.users': 'user_id'}

    user_id = fields.Many2one('res.users',string='Related User', required=True,
        ondelete='cascade', help='User-related data of the physician')
    code = fields.Char(string='Physician Code', default='/', tracking=True)
    degree_ids = fields.Many2many('physician.degree', 'physician_rel_education', 'physician_ids','degree_ids', string='Degree')
    specialty_id = fields.Many2one('physician.specialty', ondelete='set null', string='Specialty', help='Specialty Code', tracking=True)
    medical_license = fields.Char(string='Medical License', tracking=True)

    def _post_model_setup__(self):  # noqa: PLW3201
        # Fields of res.users mirroring hr.employee (hr's related_employee_field)
        # get their label in res.users._post_model_setup__; the copies inherited
        # through _inherits keep the '__default__' placeholder, resolve it here.
        registry = self.env.registry
        if 'hr.employee' in registry:
            user_fields = registry['res.users']._fields
            employee_fields = registry['hr.employee']._fields
            for field in self._fields.values():
                if field.string != '__default__' or not field.inherited:
                    continue
                user_field = user_fields.get(field.name)
                employee_field_name = getattr(getattr(user_field, 'compute', None), 'employee_field_name', None)
                if employee_field_name in employee_fields:
                    field.string = employee_fields[employee_field_name].string
                    if field.help is None:
                        field.help = employee_fields[employee_field_name].help
        return super()._post_model_setup__()

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get('code','/') == '/':
                values['code'] = self.env['ir.sequence'].next_by_code('hms.physician')
            if values.get('email'):
                values['login'] = values.get('email')

            #PB: It creates issue in physican creation
            if values.get('user_ids'):
                values.pop('user_ids')

        return super(Physician, self).create(vals_list)

class ResUsers(models.Model):
    _inherit = 'res.users'

    # inverse of hms.physician.user_id, used by the ir.access domain letting
    # HMS managers update the user records behind physicians
    pb_hms_physician_ids = fields.One2many('hms.physician', 'user_id', string='HMS Physicians')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
