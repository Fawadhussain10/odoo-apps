# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class WhatsappSendWizard(models.TransientModel):
    _name = 'whatsapp.send.wizard'
    _description = 'Send WhatsApp Message'

    account_id = fields.Many2one(
        'whatsapp.account', string='Send From', required=True,
        domain="[('state', '=', 'connected')]",
        default=lambda self: self.env['whatsapp.account']._get_linked_accounts()[:1])
    phone = fields.Char(string='To (phone)', required=True)
    message = fields.Text()
    res_model = fields.Char()
    res_id = fields.Integer()
    report_xmlid = fields.Char()
    pdf_filename = fields.Char(string='File name')
    attach_pdf = fields.Boolean(string='Attach PDF', default=True)

    def action_send(self):
        self.ensure_one()
        attachment = None
        if self.report_xmlid and self.attach_pdf and self.res_id:
            attachment = self._render_attachment()
        if not (self.message or '').strip() and not attachment:
            raise UserError(_("Please write a message."))
        result = self.env['whatsapp.account'].send_message(
            self.phone, self.message or '', account=self.account_id,
            res_model=self.res_model, res_id=self.res_id, attachment=attachment)
        return self.env['whatsapp.account']._notification_for(result)

    def _render_attachment(self):
        """The document's PDF, rendered with the current user's access rights."""
        report = self.env.ref(self.report_xmlid, raise_if_not_found=False)
        if not report:
            return None
        try:
            content, _fmt = self.env['ir.actions.report']._render_qweb_pdf(
                report, [self.res_id])
        except UserError:
            raise
        except Exception as exc:
            raise UserError(_(
                "The PDF could not be created (%s). Untick 'Attach PDF' to send the "
                "message only.", exc))
        return {'filename': self.pdf_filename or 'document.pdf', 'content': content,
                'mimetype': 'application/pdf'}
