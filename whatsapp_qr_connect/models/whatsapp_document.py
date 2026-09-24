# -*- coding: utf-8 -*-
"""WhatsApp buttons on business documents.

The module only depends on ``base``, ``web`` and ``account``. Buttons for
Sales, Purchase, Inventory (delivery / receipt) and Payroll documents are added
at registry load time, and only for the apps that are actually installed, so
the same module installs on any database.

For every supported document a server action and an inheriting form view (with
a "WhatsApp" button) are created once; they are keyed by external ids of this
module, so uninstalling the module removes them again.
"""
import logging
import re

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MODULE = 'whatsapp_qr_connect'

INVOICE_TYPES = "('out_invoice', 'out_refund', 'in_invoice', 'in_refund')"

# model, label, report xmlid, form view xmlid, xpath + position where the button goes,
# invisible condition, recipient phone expressions (first non-empty wins)
DOCUMENTS = [
    {
        'model': 'sale.order', 'label': 'Sales Order',
        'report': 'sale.action_report_saleorder', 'view': 'sale.view_order_form',
        'invisible': "state == 'cancel'",
        'phones': ['partner_id.phone', 'partner_id.mobile', 'partner_id.commercial_partner_id.phone'],
    },
    {
        'model': 'purchase.order', 'label': 'Purchase Order',
        'report': 'purchase.action_report_purchase_order', 'view': 'purchase.purchase_order_form',
        'invisible': "state == 'cancel'",
        'phones': ['partner_id.phone', 'partner_id.mobile', 'partner_id.commercial_partner_id.phone'],
    },
    {
        'model': 'stock.picking', 'label': 'Delivery / Receipt',
        'report': 'stock.action_report_delivery', 'view': 'stock.view_picking_form',
        'invisible': "state == 'cancel'",
        'phones': ['partner_id.phone', 'partner_id.mobile', 'partner_id.commercial_partner_id.phone'],
    },
    {
        'model': 'account.move', 'label': 'Invoice / Bill',
        'report': 'account.account_invoices', 'view': 'account.view_move_form',
        'invisible': "move_type not in %s or state != 'posted'" % INVOICE_TYPES,
        'phones': ['partner_id.phone', 'partner_id.mobile', 'partner_id.commercial_partner_id.phone'],
    },
    {
        'model': 'hr.payslip', 'label': 'Salary Slip',
        'report': 'hr_payroll.action_report_payslip', 'view': 'hr_payroll.view_hr_payslip_form',
        'invisible': "state == 'cancel'",
        'phones': ['employee_id.mobile_phone', 'employee_id.work_phone', 'employee_id.private_phone'],
    },
    {
        # Contacts: customer / vendor ledger. Uses this module's own report, so it
        # works without the Enterprise accounting reports.
        'model': 'res.partner', 'label': 'Customer Ledger',
        'report': '%s.action_report_partner_ledger' % MODULE, 'view': 'base.view_partner_form',
        'place': 'button_box',
        'invisible': "not id",
        'phones': ['phone', 'mobile', 'commercial_partner_id.phone'],
    },
]
DOCUMENT_BY_MODEL = {d['model']: d for d in DOCUMENTS}


def _money(record, amount, currency=None):
    currency = currency or (record.currency_id if 'currency_id' in record._fields else record.env.company.currency_id)
    return '%s %s' % (currency.symbol or currency.name or '', '{:,.2f}'.format(amount or 0.0))


def _company(record):
    return (record.company_id.name if 'company_id' in record._fields and record.company_id
            else record.env.company.name) or ''


def _msg_sale(rec):
    kind = _('quotation') if rec.state in ('draft', 'sent') else _('sales order')
    return _("Hello %(partner)s, please find your %(kind)s %(name)s from %(company)s attached. "
             "Total: %(amount)s. Thank you!",
             partner=rec.partner_id.name or '', kind=kind, name=rec.name,
             company=_company(rec), amount=_money(rec, rec.amount_total))


def _msg_purchase(rec):
    kind = _('request for quotation') if rec.state in ('draft', 'sent', 'to approve') else _('purchase order')
    return _("Hello %(partner)s, please find our %(kind)s %(name)s from %(company)s attached. "
             "Total: %(amount)s. Thank you!",
             partner=rec.partner_id.name or '', kind=kind, name=rec.name,
             company=_company(rec), amount=_money(rec, rec.amount_total))


def _msg_picking(rec):
    if rec.picking_type_code == 'incoming':
        kind = _('receipt')
    else:
        kind = _('delivery')
    return _("Hello %(partner)s, please find the %(kind)s document %(name)s from %(company)s attached. "
             "Thank you!", partner=rec.partner_id.name or '', kind=kind, name=rec.name,
             company=_company(rec))


def _msg_move(rec):
    kinds = {
        'out_invoice': _('invoice'), 'out_refund': _('credit note'),
        'in_invoice': _('bill'), 'in_refund': _('refund'),
    }
    text = _("Hello %(partner)s, please find %(kind)s %(name)s from %(company)s attached. "
             "Amount: %(amount)s.",
             partner=rec.partner_id.name or '', kind=kinds.get(rec.move_type, _('document')),
             name=rec.name or '', company=_company(rec), amount=_money(rec, rec.amount_total))
    if rec.invoice_date_due and rec.move_type in ('out_invoice', 'in_invoice'):
        text += ' ' + _("Due date: %s.", rec.invoice_date_due)
    return text + ' ' + _("Thank you!")


def _msg_payslip(rec):
    period = '%s - %s' % (rec.date_from or '', rec.date_to or '')
    return _("Hello %(employee)s, your payslip %(name)s for %(period)s is attached. "
             "Please keep it confidential.",
             employee=rec.employee_id.name or '', name=rec.name or '', period=period)


def _msg_partner(rec):
    _lines, balance = rec.env['report.%s.report_partner_ledger' % MODULE]._ledger_lines(rec)
    company = rec.env.company
    return _("Hello %(partner)s, please find your account statement from %(company)s attached. "
             "Current balance: %(amount)s. Thank you!",
             partner=rec.name or '', company=company.name or '',
             amount=_money(rec, balance, company.currency_id))


MESSAGES = {
    'sale.order': _msg_sale,
    'purchase.order': _msg_purchase,
    'stock.picking': _msg_picking,
    'account.move': _msg_move,
    'hr.payslip': _msg_payslip,
    'res.partner': _msg_partner,
}


def _safe_name(text):
    return re.sub(r'[^\w.\-]+', '_', text or '').strip('_') or 'document'


class WhatsappDocument(models.AbstractModel):
    _name = 'whatsapp.document'
    _description = 'WhatsApp document buttons'

    # ------------------------------------------------------------------
    # Dialog opened by the buttons
    # ------------------------------------------------------------------
    @api.model
    def wa_open_dialog(self, model, res_id):
        """Open the "Send WhatsApp" dialog prefilled for a document."""
        doc = DOCUMENT_BY_MODEL.get(model)
        if not doc:
            raise UserError(_("WhatsApp sending is not available for this document."))
        Account = self.env['whatsapp.account']
        Account._check_sender()
        if not Account._get_linked_accounts():
            raise UserError(_(
                "No WhatsApp number is linked. Go to Settings > Technical > WhatsApp "
                "and scan the QR code."))
        record = self.env[model].browse(res_id).exists()
        if not record:
            raise UserError(_("This document no longer exists."))
        record.check_access('read')

        phone = ''
        for expression in doc['phones']:
            try:
                value = next(iter(record.mapped(expression)), '')
            except (KeyError, AttributeError, ValueError):
                continue
            if value:
                phone = value
                break

        report = self.env.ref(doc['report'], raise_if_not_found=False)
        ctx = {
            'default_phone': phone or '',
            'default_message': MESSAGES[model](record),
            'default_res_model': model,
            'default_res_id': record.id,
            'default_report_xmlid': doc['report'] if report else False,
            'default_pdf_filename': self._wa_pdf_filename(record),
        }
        default = Account._get_linked_accounts().filtered('is_default')[:1]
        if default:
            ctx['default_account_id'] = default.id
        return {
            'type': 'ir.actions.act_window',
            'name': _("Send WhatsApp"),
            'res_model': 'whatsapp.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }

    @api.model
    def _wa_pdf_filename(self, record):
        if record._name == 'hr.payslip':
            base = 'Payslip_%s_%s' % (record.employee_id.name or '', record.date_from or '')
        elif record._name == 'res.partner':
            base = 'Ledger_%s' % (record.name or '')
        else:
            base = getattr(record, 'name', None) or record.display_name
        return _safe_name(base) + '.pdf'

    # ------------------------------------------------------------------
    # Button installation (once per installed app)
    # ------------------------------------------------------------------
    def _register_hook(self):
        super()._register_hook()
        for doc in DOCUMENTS:
            try:
                self._wa_install_button(doc)
            except Exception:  # never break registry loading
                _logger.exception("WhatsApp: could not add the button to %s", doc['model'])

    def _wa_get_or_create(self, model, name, vals, compare):
        """Create (or refresh when ``compare`` fields differ) a record keyed by
        an external id of this module."""
        xmlid = '%s.%s' % (MODULE, name)
        record = self.env.ref(xmlid, raise_if_not_found=False)
        if record:
            changed = {}
            for field in compare:
                current = record[field]
                current = current.id if hasattr(current, 'id') else current
                if current != vals[field]:
                    changed[field] = vals[field]
            if changed:
                record.write(changed)
            return record
        record = self.env[model].create(vals)
        self.env['ir.model.data'].create({
            'module': MODULE, 'name': name, 'model': model,
            'res_id': record.id, 'noupdate': True,
        })
        return record

    def _wa_install_button(self, doc):
        env = self.env
        model = doc['model']
        if model not in env.registry:
            return
        form = env.ref(doc['view'], raise_if_not_found=False)
        if not form:
            return
        key = model.replace('.', '_')
        action = self._wa_get_or_create('ir.actions.server', 'wa_action_%s' % key, {
            'name': 'Send WhatsApp',
            'model_id': env['ir.model']._get_id(model),
            'state': 'code',
            'code': "action = env['whatsapp.document'].wa_open_dialog('%s', record.id)" % model,
        }, compare=('code', 'model_id'))
        # Any internal user may click the button (the dialog itself checks that they
        # can read the document); without a group only users who can *write* the
        # document could run the action.
        group_user = env.ref('base.group_user')
        if group_user not in action.group_ids:
            action.write({'group_ids': [(4, group_user.id)]})

        invisible = doc.get('invisible')
        invisible_attr = ' invisible="%s"' % invisible if invisible else ''
        if doc.get('place') == 'button_box':
            arch = (
                '<data><xpath expr="//div[@name=\'button_box\']" position="inside">'
                '<button name="%(action)d" type="action" class="oe_stat_button" icon="fa-whatsapp"%(inv)s>'
                '<div class="o_stat_info"><span class="o_stat_text">WhatsApp Ledger</span></div>'
                '</button></xpath></data>'
            )
        else:
            arch = (
                '<data><xpath expr="//header/field[@name=\'state\']" position="before">'
                '<button name="%(action)d" type="action" string="WhatsApp" icon="fa-whatsapp" '
                'class="btn-secondary"%(inv)s/></xpath></data>'
            )
        arch = arch % {'action': action.id, 'inv': invisible_attr}
        view = self._wa_get_or_create('ir.ui.view', 'wa_view_%s' % key, {
            'name': 'whatsapp.qr.connect.button.%s' % model,
            'model': model,
            'inherit_id': form.id,
            'mode': 'extension',
            'priority': 99,
            'arch': arch,
        }, compare=('inherit_id',))
        if 'name="%d"' % action.id not in (view.arch_db or ''):
            view.write({'arch': arch})   # the server action was recreated
