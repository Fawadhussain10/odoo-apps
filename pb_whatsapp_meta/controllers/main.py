# -*- coding: utf-8 -*-

import odoo
from odoo.http import request
from odoo import fields as odoo_fields, http, tools, _, SUPERUSER_ID
from odoo.service import common

import json
import logging
_logger = logging.getLogger(__name__)

from odoo.exceptions import AccessError, MissingError, UserError



class PbMetaWaba(http.Controller):

    @http.route('/pb/waba/webhooks', type="json", auth="public", methods=['POST','GET'], sitemap=False, csrf=False)
    def pb_waba_webhooks_data(self, **kwargs):
        json_data = request.jsonrequest
        _logger.warning('waba data: %s', json_data)

        mode = json_data.get("hub.mode")
        verify_token = json_data.get("hub.verify_token")
        challenge = json_data.get("hub.challenge")

        # lead = request.env["crm.lead"].sudo().search([('phone','=', str(kwargs.get('number')))], limit=1)
        # _logger.warning('updated lead: %s', lead)
        # if lead:
        #     lead.sudo().write(data)
        return challenge

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: