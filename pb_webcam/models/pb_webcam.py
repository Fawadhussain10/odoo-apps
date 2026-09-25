# -*- coding: utf-8 -*-
from odoo import api, fields, models

class PbWebcamMixin(models.AbstractModel):
    _name = "pb.webcam.mixin"
    _description = "PB Webcam Mixin"

    def pb_open_website_url(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/pb/webcam/' + self._name + '/' + str(self.id),
            'target': 'self',
        }


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner','pb.webcam.mixin']

    def pb_webcam_retrun_action(self):
        self.ensure_one()
        return self.env.ref('base.action_partner_form').id


class ResUsers(models.Model):
    _name = 'res.users'
    _inherit = ['res.users','pb.webcam.mixin']

    def pb_webcam_retrun_action(self):
        self.ensure_one()
        return self.env.ref('base.action_res_users').id
