from odoo import fields, models


class HrWorkflowRejectWizard(models.TransientModel):
    _name = 'hr.workflow.reject.wizard'
    _description = 'Reject HR Workflow Request'

    request_id = fields.Many2one('hr.workflow.request', required=True)
    comment = fields.Text('Reason', required=True)

    def action_reject(self):
        self.request_id._do_reject(self.comment)
        return {'type': 'ir.actions.act_window_close'}
