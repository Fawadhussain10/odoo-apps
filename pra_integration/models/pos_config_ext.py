from lxml.doctestcompare import strip
from odoo import models, fields, api

from odoo.addons.point_of_sale.models.pos_order import PosOrder


class PosConfig(models.Model):
    _inherit = 'pos.config'

    pra_integration_enabled = fields.Boolean("Enable PRA ", default=False)
    pra_sync_enabled = fields.Boolean("Enable PRA Sync", default=False)
    pra_environment = fields.Selection([
        ('test', 'Testing'),
        ('production', 'Production'),
    ], string="Environment", default='test')
    # Testing
    pra_test_api_url = fields.Char("PRA Testing API URL")
    pra_test_api_key = fields.Char("PRA Testing API Key")
    pra_test_pos_id = fields.Char("PRA Testing POS ID")
    pra_test_access_code = fields.Char("PRA Testing Access Code")
    # Production
    pra_production_api_url = fields.Char("PRA Production API URL")
    pra_production_api_key = fields.Char("PRA Production API Key")
    pra_production_pos_id = fields.Char("PRA Production POS ID")
    pra_production_access_code = fields.Char("PRA Production Access Code")
