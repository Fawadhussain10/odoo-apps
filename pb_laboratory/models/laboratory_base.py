# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PBLabTestUom(models.Model):
    _name = "pb.lab.test.uom"
    _description = "Lab Test UOM"
    _order = 'sequence asc'
    _rec_name = 'code'

    name = fields.Char(string='UOM Name', required=True)
    code = fields.Char(string='Code', required=True, index=True, help="Short name - code for the test UOM")
    sequence = fields.Integer("Sequence", default="100")

    _code_uniq = models.Constraint('unique (name)', 'The Lab Test code must be unique')


class PbLaboratory(models.Model):
    _name = 'pb.laboratory'
    _description = 'Laboratory'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'pb.hms.mixin']
    _inherits = {
        'res.partner': 'partner_id',
    }

    description = fields.Text()
    is_collection_center = fields.Boolean('Is Collection Center')
    partner_id = fields.Many2one('res.partner', 'Partner', ondelete='restrict', required=True)
    active = fields.Boolean(string="Active", default=True)


class LabTest(models.Model):
    _name = "pb.lab.test"
    _description = "Lab Test Type"
    _rec_names_search = ['name', 'code']

    name = fields.Char(string='Name', help="Test type, eg X-Ray, hemogram,biopsy...", index=True)
    code = fields.Char(string='Code', help="Short name - code for the test")
    description = fields.Text(string='Description')
    active = fields.Boolean(string="Active", default=True)
    product_id = fields.Many2one('product.product',string='Service', required=True)
    list_price = fields.Float(related='product_id.list_price', string="Price", readonly=True)
    critearea_ids = fields.One2many('lab.test.critearea','test_id', string='Test Cases')
    remark = fields.Char(string='Remark')
    report = fields.Text (string='Test Report')
    company_id = fields.Many2one('res.company', ondelete='restrict', 
        string='Company' , default=lambda self: self.env.company)
    consumable_line_ids = fields.One2many('hms.consumable.line', 'lab_test_id',
        string='Consumable Line')
    pb_tat = fields.Char(string='Turnaround Time')
    result_value_type = fields.Selection([
        ('quantitative','Quantitative'),
        ('qualitative','Qualitative'),
    ], string='Result Type', default='quantitative')
    sample_type_id = fields.Many2one('pb.laboratory.sample.type', string='Sample Type')
    pb_use_other_test_sample = fields.Boolean(string="Share Sample with Other Tests", default=True)
    subsequent_test_ids = fields.Many2many("pb.lab.test", "pb_lab_test_rel", "test_id", "sub_test_id", "Subsequent Tests")

    _code_company_uniq = models.Constraint('unique (code,company_id)', 'The code of the account must be unique per company !')

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for rec in self:
            name = rec.name or ''
            if rec.code:
                name = "%s [%s]" % (rec.name, rec.code)
            rec.display_name = name

    def copy(self, default=None):
        self.ensure_one()
        new_name = _('%s (copy)') % self.name
        new_code = _('%s (copy)') % self.code
        default = dict(default or {}, name=new_name, code=new_code)
        return super(LabTest, self).copy(default)


class LabTestCritearea(models.Model):
    _name = "lab.test.critearea"
    _description = "Lab Test Criteria"
    _order="sequence, id asc"

    name = fields.Char('Parameter')
    sequence = fields.Integer('Sequence',default=100)
    result = fields.Char('Result')
    lab_uom_id = fields.Many2one('pb.lab.test.uom', string='UOM')
    remark = fields.Char('Remark')
    normal_range = fields.Char('Normal Range')
    normal_range_male = fields.Char('Normal Range (Male)')
    normal_range_female = fields.Char('Normal Range (Female)')
    test_id = fields.Many2one('pb.lab.test','Test type', ondelete='cascade')
    patient_lab_id = fields.Many2one('patient.laboratory.test','Lab Test', ondelete='cascade')
    request_id = fields.Many2one('pb.laboratory.request', 'Lab Request', ondelete='cascade')
    company_id = fields.Many2one('res.company', ondelete='restrict', 
        string='Company', default=lambda self: self.env.company)
    display_type = fields.Selection([
        ('line_section', "Section")], help="Technical field for UX purpose.")
    result_type = fields.Selection([
        ('low', "Low"),
        ('normal', "Normal"),
        ('high', "High"),
        ('positive', "Positive"),
        ('negative', "Negative")], default='normal', string="Result Type", help="Technical field for UI purpose.")
    result_value_type = fields.Selection([
        ('quantitative','Quantitative'),
        ('qualitative','Qualitative'),
    ], string='Result Value Type', default='quantitative')

    @api.onchange('normal_range_male')
    def onchange_normal_range_male(self):
        if self.normal_range_male and not self.normal_range_female:
            self.normal_range_female = self.normal_range_male

    @api.onchange('result')
    def onchange_result(self):
        if self.result and self.result_value_type=='quantitative' and self.normal_range:
            try:
                split_value = self.normal_range.split('-')
                low_range = high_range = 0
                result = float(self.result)
                if len(split_value)==2:
                    low_range = float(split_value[0])
                    high_range = float(split_value[1])
                elif len(split_value)==2:
                    low_range = float(split_value[0])
                    high_range = float(split_value[0])

                if low_range or high_range:
                    if result < low_range:
                        self.result_type = 'low'
                    elif result > high_range:
                        self.result_type = 'high'
                    elif result > low_range and result < high_range:
                        self.result_type = 'normal'
                    elif result==low_range or result==high_range:
                        self.result_type = 'warning'
            except:
                pass


class PatientLabSample(models.Model):
    _name = "pb.patient.laboratory.sample"
    _description = "Patient Laboratory Sample"
    _order = 'date desc, id desc'

    STATES = {'cancel': [('readonly', True)], 'examine': [('readonly', True)], 'collect': [('readonly', True)]}

    name = fields.Char(string='Name', help="Sample Name", readonly=True, copy=False, index=True)
    patient_id = fields.Many2one('hms.patient', string='Patient', required=True)
    user_id = fields.Many2one('res.users',string='User', default=lambda self: self.env.user)
    date = fields.Datetime(string='Date', default=fields.Datetime.now)
    request_id = fields.Many2one('pb.laboratory.request', string='Lab Request', ondelete='restrict', required=True)
    company_id = fields.Many2one('res.company', ondelete='restrict', 
        string='Company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft','Draft'),
        ('collect', 'Collected'),
        ('examine', 'Examined'),
        ('cancel','Cancel'),
    ], string='Status',readonly=True, default='draft')
    sample_type_id = fields.Many2one('pb.laboratory.sample.type', string='Sample Type', required=True)
    container_name = fields.Char(string='Sample Container Code', help="If using preprinted sample tube/slide/box no can be updated here.", copy=False, index=True)
    patient_test_ids = fields.Many2many('patient.laboratory.test', 'test_lab_sample_rel', 'sample_id', 'test_id', string="Patient Lab Tests")
    test_ids = fields.Many2many('pb.lab.test', 'pb_test_lab_sample_rel', 'sample_id', 'test_id', string="Lab Tests")

    notes = fields.Text(string='Notes')

    #Just to make object selectable in selction field this is required: Waiting Screen
    pb_show_in_wc = fields.Boolean(default=True)

    _name_company_uniq = models.Constraint('unique (name,company_id)', 'Sample Name must be unique per company !')

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values['name'] = self.env['ir.sequence'].next_by_code('pb.patient.laboratory.sample')
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.state not in ['draft']:
                raise UserError(_("Record can be delete only in Draft state."))
        return super(PatientLabSample, self).unlink()

    @api.onchange('request_id')
    def onchange_request_id(self):
        if self.request_id:
            self.patient_id = self.request_id.patient_id.id

    def action_collect(self):
        self.state = 'collect'

    def action_examine(self):
        self.state = 'examine'

    def action_cancel(self):
        self.state = 'cancel'


class LaboratoryGroupLine(models.Model):
    _name = "laboratory.group.line"
    _description = "Laboratory Group Line"

    group_id = fields.Many2one('laboratory.group', ondelete='restrict', string='Laboratory Group')
    test_id = fields.Many2one('pb.lab.test',string='Test', ondelete='cascade', required=True)
    pb_tat = fields.Char(related='test_id.pb_tat', string='Turnaround Time', readonly=True)
    instruction = fields.Char(string='Special Instructions')
    sale_price = fields.Float(string='Sale Price')

    @api.onchange('test_id')
    def onchange_test(self):
        if self.test_id:
            self.sale_price = self.test_id.product_id.lst_price


class LaboratoryGroup(models.Model):
    _name = "laboratory.group"
    _description = "Laboratory Group"

    name = fields.Char(string='Group Name', required=True)
    line_ids = fields.One2many('laboratory.group.line', 'group_id', string='Medicament line')


class LabSampleType(models.Model):
    _name = "pb.laboratory.sample.type"
    _description = "Laboratory Sample Type"
    _order = 'sequence asc'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer("Sequence", default="100")
    description = fields.Text("Description")

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: