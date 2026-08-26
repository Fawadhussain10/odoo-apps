# -*- coding: utf-8 -*-

from odoo import api, fields, models ,_
from odoo.exceptions import UserError


class PbDentalQuestionnaireTemplate(models.Model):
    _name="pb.dental.questionnaire.template"
    _description = "Dental Questionnaire Template"

    name = fields.Char(string="Name", required=True)
    remark = fields.Char(string="Remarks")
    question_type = fields.Selection([('medical', 'Medical'),
        ('dental', 'Dental')], default="dental", required=True)


class PbDentalQuestionnaire(models.Model):
    _name="pb.dental.questionnaire"
    _description = "Dental Questionnaire"

    name = fields.Char(string="Name", required=True)
    is_done = fields.Boolean(string="Y/N")
    remark = fields.Char(string="Remarks")
    appointment_id = fields.Many2one("hms.appointment", ondelete="cascade", string="Appointment")


class PbmedicalQuestionnaire(models.Model):
    _name="pb.medical.questionnaire"
    _description = "Medical Questionnaire"

    name = fields.Char(string="Name", required=True)
    is_done = fields.Boolean(string="Y/N")
    remark = fields.Char(string="Remarks")
    appointment_id = fields.Many2one("hms.appointment", ondelete="cascade", string="Appointment")


class PbHmsTooth(models.Model):
    _name="pb.hms.tooth"
    _description = "Tooth"
    _order = "sequence,id"

    name = fields.Char(string="Name", required=True)
    number = fields.Char(string="Number", required=True)
    fdi_code = fields.Char(string="FDI", required=True)
    quadrant = fields.Selection([
        ('upper_right', 'Upper Right'),
        ('upper_left', 'Upper Left'),
        ('lower_right', 'Lower Right'),
        ('lower_left', 'Lower Left')], default="upper_right", required=True)
    sequence = fields.Integer(string="Sequence", default=50)

    @api.depends('number', 'name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.number + '. ' + rec.name


class PbToothSurface(models.Model):
    _name="pb.tooth.surface"
    _description = "Tooth Surface"
    _order = "sequence"

    name = fields.Char(string="Name", required=True)
    sequence = fields.Integer(string="Sequence", default="50")
    description = fields.Text(string="Description")

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:   