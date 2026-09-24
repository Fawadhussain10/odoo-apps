# -*- coding: utf-8 -*-
import base64
import io
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone

from odoo import _, api, fields, models, modules, sql_db
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

WORKER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'worker', 'whatsapp_worker.py',
)
LINK_TIMEOUT = 170          # seconds a QR code stays scannable (see worker)
STALE_LINK_AFTER = LINK_TIMEOUT + 40
CONNECT_TIMEOUT = 30
RECEIVE_WINDOW = 12
PER_MESSAGE_TIMEOUT = 20
PER_ATTACHMENT_TIMEOUT = 60
LOCK_NAMESPACE = 0x57410000  # advisory lock key = namespace + account id


def _qr_png_b64(env, text):
    """Base64 PNG of a QR code, without needing a graphics backend on the server.

    Tries, in order: ``segno`` (pure Python; installed together with ``neonize``),
    then ``qrcode`` (used by several Odoo apps; needs Pillow), and finally Odoo's
    reportlab barcode renderer, which needs ``rlPyCairo``/``pycairo`` and is not
    available on every host (e.g. Odoo.sh)."""
    try:
        import segno
        buf = io.BytesIO()
        segno.make(text, error='m').save(buf, kind='png', scale=8, border=2)
        return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        pass
    try:
        import qrcode
        image = qrcode.make(text, error_correction=qrcode.constants.ERROR_CORRECT_M,
                            box_size=8, border=2)
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        pass
    png = env['ir.actions.report'].barcode('QR', text, width=360, height=360, barBorder=2)
    return base64.b64encode(png).decode()


class WhatsappAccount(models.Model):
    _name = 'whatsapp.account'
    _description = 'WhatsApp Account (linked number)'
    _order = 'sequence, id'

    name = fields.Char(string='Label', required=True,
                       help="A name to recognise this number, e.g. 'Sales' or 'Support'.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company,
        help="Leave empty to make this number available to every company.")
    phone = fields.Char(string='WhatsApp Number', readonly=True, copy=False)
    push_name = fields.Char(string='WhatsApp Profile Name', readonly=True, copy=False)
    state = fields.Selection([
        ('draft', 'Not Linked'),
        ('linking', 'Waiting for QR Scan'),
        ('connected', 'Linked'),
        ('disconnected', 'Logged Out'),
    ], default='draft', required=True, readonly=True, copy=False)
    is_default = fields.Boolean(
        string='Default Number',
        help="Used when a message is sent without choosing a number and more "
             "than one number is linked.")
    last_connected = fields.Datetime(readonly=True, copy=False)
    last_error = fields.Text(readonly=True, copy=False)
    listen_stop = fields.Boolean(copy=False, groups='base.group_system',
                                 help="Set by Odoo to make the background listener release the session.")
    link_pid = fields.Integer(readonly=True, copy=False, groups='base.group_system')
    qr_string = fields.Char(readonly=True, copy=False, groups='base.group_system')
    session_data = fields.Binary(
        attachment=False, readonly=True, copy=False, groups='base.group_system',
        help="The WhatsApp login of this number. Treat it like a password.")
    message_count = fields.Integer(compute='_compute_message_count')

    def _compute_message_count(self):
        data = self.env['whatsapp.message'].sudo()._read_group(
            [('account_id', 'in', self.ids)], ['account_id'], ['__count'])
        counts = {account.id: count for account, count in data}
        for rec in self:
            rec.message_count = counts.get(rec.id, 0)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _check_admin(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only administrators can manage WhatsApp numbers."))

    @api.model
    def _check_sender(self):
        if not self.env.user._is_internal():
            raise AccessError(_("Only internal users can send WhatsApp messages."))

    @api.model
    def _normalize_phone(self, phone):
        """Digits only, international format, or ``None`` if unusable.

        Set the system parameter ``whatsapp_qr_connect.default_country_code``
        (e.g. ``92``) to also accept local numbers that start with ``0``.
        """
        digits = re.sub(r'\D', '', phone or '')
        if digits.startswith('00'):
            digits = digits[2:]
        country = re.sub(r'\D', '', self.env['ir.config_parameter'].sudo().get_param(
            'whatsapp_qr_connect.default_country_code') or '')
        if country and digits.startswith('0'):
            digits = country + digits.lstrip('0')
        return digits if 8 <= len(digits) <= 15 else None

    def _python_bin(self):
        return (self.env['ir.config_parameter'].sudo().get_param(
            'whatsapp_qr_connect.python_path') or sys.executable)

    def _check_worker_python(self):
        """Fail early, with instructions, when the interpreter that runs the
        WhatsApp helper cannot import ``neonize``."""
        python = self._python_bin()
        try:
            proc = subprocess.run(
                [python, '-c', 'import neonize, psycopg2'],
                capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UserError(_("The Python interpreter for WhatsApp (%(python)s) cannot be started: %(error)s",
                              python=python, error=exc))
        if proc.returncode:
            detail = ((proc.stderr or '').strip().splitlines() or [''])[-1]
            raise UserError(_(
                "The Python library 'neonize' (version 0.5.2, needs protobuf 7.34.1 or newer) cannot be "
                "loaded by %(python)s.\n\n%(detail)s\n\nInstall it there (pip install neonize==0.5.2 "
                "psycopg2-binary), or install it in a separate virtualenv and set the system parameter "
                "'whatsapp_qr_connect.python_path' to that virtualenv's python.",
                python=python, detail=detail))

    def _worker_config(self, mode, payload=None, **extra):
        dbname, params = sql_db.connection_info_for(self.env.cr.dbname)
        return dict({
            'db': {'name': dbname, 'params': params},
            'account_id': self.id,
            'mode': mode,
            'payload': payload or {},
        }, **extra)

    def _worker_env(self, cfg):
        env = dict(os.environ)
        env['WA_WORKER_CONFIG'] = json.dumps(cfg)
        return env

    def _run_worker(self, mode, payload=None, timeout=90, **extra):
        """Run the helper synchronously; returns the JSON dict it printed."""
        self.ensure_one()
        cfg = self._worker_config(mode, payload, **extra)
        try:
            proc = subprocess.run(
                [self._python_bin(), WORKER], env=self._worker_env(cfg),
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {'ok': False, 'code': 'TIMEOUT',
                    'error': _("WhatsApp did not answer in time.")}
        except OSError as exc:
            return {'ok': False, 'code': 'ERROR', 'error': str(exc)}
        result = None
        for line in reversed((proc.stdout or '').splitlines()):
            line = line.strip()
            if line.startswith('{'):
                try:
                    result = json.loads(line)
                    break
                except ValueError:
                    continue
        for line in (proc.stderr or '').splitlines():
            if line.startswith('receive:'):
                _logger.info("WhatsApp worker (%s): %s", mode, line)
        if result is None:
            tail = ((proc.stderr or '').strip().splitlines() or [''])[-1]
            _logger.warning("WhatsApp worker (%s) failed: %s", mode, proc.stderr)
            if 'No module named' in (proc.stderr or ''):
                tail = _("The 'neonize' Python package is not installed for %s.",
                         self._python_bin())
            return {'ok': False, 'code': 'ERROR', 'error': tail or _("WhatsApp helper failed.")}
        return result

    def _lock(self):
        """Serialise use of one WhatsApp session (two live connections of the
        same device would kick each other out)."""
        self._request_listener_stop()
        self.env.cr.execute("SELECT pg_advisory_xact_lock(%s)", [LOCK_NAMESPACE + self.id])

    def _request_listener_stop(self):
        """The background listener keeps the WhatsApp connection open; ask it (through a
        separate, immediately committed transaction) to let go so this operation can run."""
        with self.env.registry.cursor() as cr:
            cr.execute("UPDATE whatsapp_account SET listen_stop = true WHERE id = %s", [self.id])

    # ------------------------------------------------------------------
    # Linking (QR code)
    # ------------------------------------------------------------------
    def action_link(self):
        """Start (or resume) linking this number and open the QR screen."""
        self.ensure_one()
        self._check_admin()
        if self.state == 'connected':
            raise UserError(_("This number is already linked."))
        if not self._link_running():
            self._check_worker_python()
            # Commit so the helper process (own DB connection) sees the record.
            self.write({'state': 'linking', 'last_error': False})
            if not modules.module.current_test:
                self.env.cr.commit()
            self._spawn_link_worker()
        return self._link_action()

    def _link_action(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'whatsapp_qr_connect.link_action',
            'name': _("Link WhatsApp"),
            'params': {'account_id': self.id},
        }

    def _link_running(self):
        return self.state == 'linking' and self.link_pid and self._pid_alive(self.link_pid)

    @staticmethod
    def _pid_alive(pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _spawn_link_worker(self):
        cfg = self._worker_config('link', timeout=LINK_TIMEOUT)
        log_path = os.path.join(tempfile.gettempdir(), 'whatsapp_qr_connect_%s.log' % self.id)
        try:
            log_file = open(log_path, 'ab')
        except OSError:
            log_file = subprocess.DEVNULL
        proc = subprocess.Popen(
            [self._python_bin(), WORKER], env=self._worker_env(cfg),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log_file,
            start_new_session=True,
        )
        # Reap the child when it ends so no zombie is left behind.
        threading.Thread(target=proc.wait, daemon=True).start()

    def get_link_status(self):
        """Polled by the QR screen every couple of seconds."""
        self.ensure_one()
        self._check_admin()
        rec = self.sudo()
        state = rec.state
        if state == 'linking' and rec.link_pid and not self._pid_alive(rec.link_pid):
            # The helper died without reporting (e.g. server restart).
            rec.write({'state': 'draft', 'link_pid': 0,
                       'last_error': _("Linking was interrupted. Please try again.")})
            state = 'draft'
        qr_image = False
        if state == 'linking' and rec.qr_string:
            qr_image = _qr_png_b64(self.env, rec.qr_string)
        return {
            'state': state,
            'qr_image': qr_image,
            'phone': rec.phone,
            'error': rec.last_error or False,
        }

    def action_cancel_link(self):
        self.ensure_one()
        self._check_admin()
        rec = self.sudo()
        if rec.link_pid:
            try:
                os.kill(rec.link_pid, signal.SIGTERM)
            except OSError:
                pass
        rec.write({'state': 'draft', 'qr_string': False, 'link_pid': 0})
        return {'type': 'ir.actions.act_window_close'}

    def action_new_number(self):
        """List-view header button: create a fresh number and show its QR code.
        (A regular method on purpose: the web client always sends the selected
        ids - none here - as first argument for object buttons.)"""
        self._check_admin()
        count = self.with_context(active_test=False).search_count([]) + 1
        account = self.create({'name': _("WhatsApp %s", count)})
        return account.action_link()

    @api.model
    def action_open_accounts(self):
        """Menu entry. Nothing linked yet -> go straight to the QR code;
        otherwise show the list of numbers."""
        self._check_admin()
        if not self.search_count([('state', '=', 'connected')]):
            unlinked = self.search([('state', '!=', 'connected')], limit=1)
            if not unlinked:
                unlinked = self.create({'name': _("WhatsApp 1")})
            return unlinked.action_link()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'whatsapp_qr_connect.action_whatsapp_account')
        return action

    def action_logout(self):
        """Unlink the number from WhatsApp and wipe its stored session."""
        self.ensure_one()
        self._check_admin()
        self._lock()
        result = self._run_worker('logout', timeout=CONNECT_TIMEOUT + 20)
        warning = result.get('warning') or result.get('error')
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _("WhatsApp"),
                'message': warning or _("The number was unlinked."),
                'type': 'warning' if warning else 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_check_connection(self):
        self.ensure_one()
        self._check_admin()
        self._lock()
        result = self._run_worker('check', timeout=CONNECT_TIMEOUT + 20)
        ok = result.get('ok')
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _("WhatsApp"),
                'message': _("Connection is working.") if ok else (
                    result.get('error') or _("Could not connect.")),
                'type': 'success' if ok else 'danger',
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_send_test(self):
        self.ensure_one()
        return self.env['whatsapp.account'].action_send_message(
            '', _("Test message from Odoo (%s)", self.name),
            account=self, force_wizard=True)

    def action_view_messages(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Messages"),
            'res_model': 'whatsapp.message',
            'view_mode': 'list,form',
            'domain': [('account_id', '=', self.id)],
        }

    def action_set_default(self):
        self.ensure_one()
        self._check_admin()
        self.search([('is_default', '=', True)]).write({'is_default': False})
        self.is_default = True

    def unlink(self):
        for rec in self:
            if rec.link_pid:
                try:
                    os.kill(rec.link_pid, signal.SIGTERM)
                except OSError:
                    pass
        return super().unlink()

    # ------------------------------------------------------------------
    # Public API for other modules
    # ------------------------------------------------------------------
    @api.model
    def _get_linked_accounts(self):
        return self.search([('state', '=', 'connected')], order='is_default desc, sequence, id')

    @api.model
    def _resolve_account(self, account=None):
        if account:
            account = self.browse(account) if isinstance(account, int) else account
            account = account.sudo()
            if account.state != 'connected':
                raise UserError(_("The WhatsApp number '%s' is not linked.", account.name))
            return account
        accounts = self._get_linked_accounts()
        if not accounts:
            raise UserError(_(
                "No WhatsApp number is linked. Go to Settings > Technical > WhatsApp "
                "and scan the QR code."))
        return accounts[0].sudo()

    @api.model
    def send_message(self, phone, message, account=None, res_model=None, res_id=None,
                     raise_on_error=False, attachment=None):
        """Send one WhatsApp text message.

        :param phone: any format; digits are extracted (see ``_normalize_phone``)
        :param account: ``whatsapp.account`` record or id. Omitted: the default
            number (or the only / first linked one).
        :param res_model, res_id: optional document the message relates to
        :param raise_on_error: raise ``UserError`` instead of returning the failure
        :param attachment: optional file sent with the message (the message becomes its
            caption): ``{'filename': 'Invoice.pdf', 'content': <bytes>, 'mimetype': 'application/pdf'}``
        :return: dict ``{'status', 'detail', 'account_id', 'message_id', 'log_id'}``
            with ``status`` one of ``SENT``, ``NOT_WHATSAPP``, ``INVALID_PHONE``,
            ``NOT_LINKED``, ``ERROR``.
        """
        return self.send_messages(
            [{'phone': phone, 'message': message, 'res_model': res_model, 'res_id': res_id,
              'attachment': attachment}],
            account=account, raise_on_error=raise_on_error)[0]

    @api.model
    def send_messages(self, items, account=None, raise_on_error=False):
        """Send several messages over one connection (much faster than
        calling :meth:`send_message` in a loop). ``items`` is a list of dicts
        with ``phone`` and ``message`` (and optionally ``res_model``/``res_id``).
        Returns a list of result dicts in the same order."""
        self._check_sender()
        account = self._resolve_account(account)
        results = [None] * len(items)
        outgoing = []
        for index, item in enumerate(items):
            number = self._normalize_phone(item.get('phone'))
            text = item.get('message') or ''
            if not number:
                results[index] = {'status': 'INVALID_PHONE',
                                  'detail': _("Invalid phone number: %s", item.get('phone') or '')}
            elif not text.strip() and not item.get('attachment'):
                results[index] = {'status': 'ERROR', 'detail': _("The message is empty.")}
            else:
                outgoing.append((index, number, text))

        if outgoing:
            account._lock()
            tmp_dir = tempfile.mkdtemp(prefix='wa_att_')
            try:
                payload, timeout = [], CONNECT_TIMEOUT + 20
                for index, number, text in outgoing:
                    entry = {'to': number, 'text': text}
                    att = items[index].get('attachment')
                    if att:
                        path = os.path.join(tmp_dir, '%d_%s' % (index, re.sub(
                            r'[^\w.\-]+', '_', att.get('filename') or 'file')))
                        with open(path, 'wb') as fh:
                            fh.write(att['content'])
                        entry['attachment'] = {
                            'path': path, 'filename': att.get('filename') or 'file',
                            'mimetype': att.get('mimetype') or 'application/pdf',
                            'as_media': bool(att.get('as_media'))}
                        timeout += PER_ATTACHMENT_TIMEOUT
                    else:
                        timeout += PER_MESSAGE_TIMEOUT
                    payload.append(entry)
                known = self.env['whatsapp.chat'].sudo().search(
                    [('account_id', '=', account.id)]).mapped('phone')
                worker = account._run_worker(
                    'send', {'messages': payload, 'known': known, 'media_dir': tmp_dir}, timeout=timeout)
                # replies that reached this connection must not be lost
                if worker.get('messages'):
                    account._process_incoming(worker['messages'])
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            worker_results = worker.get('results') if worker.get('ok') else None
            for position, (index, _number, _text) in enumerate(outgoing):
                if worker_results and position < len(worker_results):
                    results[index] = dict(worker_results[position])
                else:
                    results[index] = {
                        'status': 'NOT_LINKED' if worker.get('code') == 'NOT_LINKED' else 'ERROR',
                        'detail': worker.get('error') or _("Sending failed."),
                    }

        log_model = self.env['whatsapp.message'].sudo()
        for index, item in enumerate(items):
            res = results[index]
            res['account_id'] = account.id
            log = log_model.create({
                'account_id': account.id,
                'phone': item.get('phone'),
                'body': item.get('message'),
                'status': res['status'],
                'detail': res.get('detail'),
                'message_id': res.get('message_id'),
                'res_model': item.get('res_model'),
                'res_id': item.get('res_id') or 0,
                'attachment_name': (item.get('attachment') or {}).get('filename'),
            })
            res['log_id'] = log.id
            att = item.get('attachment') or {}
            if att.get('keep') and res['status'] == 'SENT':
                # chat screen: keep the file so the conversation can show it
                log.attachment_id = self.env['ir.attachment'].sudo().create({
                    'name': att.get('filename') or 'file', 'raw': att['content'],
                    'mimetype': att.get('mimetype') or 'application/octet-stream',
                    'res_model': 'whatsapp.message', 'res_id': log.id})
            res.setdefault('detail', False)
            res.setdefault('message_id', False)

        if raise_on_error:
            failed = [r for r in results if r['status'] != 'SENT']
            if failed:
                raise UserError(failed[0].get('detail') or failed[0]['status'])
        return results

    @api.model
    def action_send_message(self, phone, message, res_model=None, res_id=None,
                            account=None, force_wizard=False):
        """UI helper for other modules' buttons.

        Opens the "Send WhatsApp" dialog when a choice must be made (more than
        one number linked, or ``force_wizard``); otherwise sends right away and
        returns a notification action."""
        self._check_sender()
        linked = self._get_linked_accounts()
        if not linked:
            raise UserError(_(
                "No WhatsApp number is linked. Go to Settings > Technical > WhatsApp "
                "and scan the QR code."))
        if force_wizard or len(linked) > 1 and not account:
            ctx = {
                'default_phone': phone or '',
                'default_message': message or '',
                'default_res_model': res_model or False,
                'default_res_id': res_id or 0,
            }
            if account:
                ctx['default_account_id'] = account.id
            elif linked.filtered('is_default'):
                ctx['default_account_id'] = linked.filtered('is_default')[0].id
            return {
                'type': 'ir.actions.act_window',
                'name': _("Send WhatsApp"),
                'res_model': 'whatsapp.send.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': ctx,
            }
        result = self.send_message(phone, message, account=account,
                                   res_model=res_model, res_id=res_id)
        return self._notification_for(result)

    @api.model
    def _notification_for(self, result):
        ok = result['status'] == 'SENT'
        messages = {
            'SENT': _("WhatsApp message sent."),
            'NOT_WHATSAPP': _("This number is not on WhatsApp."),
            'INVALID_PHONE': _("The phone number is not valid."),
            'NOT_LINKED': _("The WhatsApp number is no longer linked."),
        }
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _("WhatsApp"),
                'message': messages.get(result['status']) or result.get('detail')
                or _("Sending failed."),
                'type': 'success' if ok else 'warning',
                'sticky': not ok,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    # ------------------------------------------------------------------
    # Receiving (chat screen)
    # ------------------------------------------------------------------
    def _stream_worker(self, mode, payload, timeout, on_message):
        """Run the helper and call ``on_message(item)`` for every ``MSG`` line as soon
        as it is printed (so replies show up live, not when the helper ends)."""
        self.ensure_one()
        cfg = self._worker_config(mode, payload)
        errors = tempfile.TemporaryFile('w+')
        proc = subprocess.Popen(
            [self._python_bin(), WORKER], env=self._worker_env(cfg),
            stdout=subprocess.PIPE, stderr=errors, text=True)
        timer = threading.Timer(timeout, proc.kill)
        timer.start()
        result = None
        try:
            for line in proc.stdout:
                line = line.strip()
                if line.startswith('MSG '):
                    try:
                        item = json.loads(line[4:])
                    except ValueError:
                        continue
                    on_message(item)
                elif line.startswith('{'):
                    try:
                        result = json.loads(line)
                    except ValueError:
                        continue
        finally:
            timer.cancel()
            proc.stdout.close()
            proc.wait()
        if result is None:
            errors.seek(0)
            tail = (errors.read().strip().splitlines() or [''])[-1]
            result = {'ok': False, 'error': tail or _("WhatsApp helper failed.")}
        errors.close()
        return result

    def _receive_messages(self, commit=False, window=RECEIVE_WINDOW):
        """Stay connected for ``window`` seconds and store replies of the numbers Odoo
        has chatted with as they arrive. Returns the number of new messages."""
        total = 0
        for account in self:
            known = self.env['whatsapp.chat'].sudo().search(
                [('account_id', '=', account.id)]).mapped('phone')
            if not known:
                continue
            self.env.cr.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_NAMESPACE + account.id])
            if not self.env.cr.fetchone()[0]:
                continue        # a send / check is using the session right now
            media_dir = tempfile.mkdtemp(prefix='wa_media_')
            try:
                with self.env.registry.cursor() as cr:
                    cr.execute("UPDATE whatsapp_account SET listen_stop = false WHERE id = %s",
                               [account.id])
                if commit and not modules.module.current_test:
                    self.env.cr.commit()        # do not sit in a transaction while listening

                def store(item, account=account):
                    nonlocal total
                    total += account._process_incoming([item])
                    if commit and not modules.module.current_test:
                        self.env.cr.commit()

                result = account._stream_worker(
                    'receive', {'known': known, 'window': window, 'media_dir': media_dir},
                    timeout=CONNECT_TIMEOUT + window + 60, on_message=store)
                if not result.get('ok'):
                    _logger.info("WhatsApp receive on %s failed: %s", account.name, result.get('error'))
            finally:
                shutil.rmtree(media_dir, ignore_errors=True)
                self.env.cr.execute("SELECT pg_advisory_unlock(%s)", [LOCK_NAMESPACE + account.id])
        return total

    def _notify_users(self, chat, message):
        """Push the new reply to every open Odoo tab through the bus websocket."""
        payload = {
            'id': message.id, 'chat_id': chat.id, 'name': chat.name,
            'text': (message.body or '[%s]' % (message.media_type or '')).replace('\n', ' ')[:80],
        }
        group = self.env.ref('whatsapp_qr_connect.group_whatsapp_chat')
        users = self.env['res.users'].sudo().search(
            [('share', '=', False), ('all_group_ids', 'in', group.ids)])
        for user in users:
            self.env['bus.bus'].sudo()._sendone(user, 'whatsapp_qr_connect.new_message', payload)

    def _store_media(self, media):
        """File saved by the helper -> attachment (read while the temp dir still exists)."""
        if not media:
            return self.env['ir.attachment']
        try:
            with open(media['path'], 'rb') as fh:
                raw = fh.read()
        except OSError:
            return self.env['ir.attachment']
        return self.env['ir.attachment'].sudo().create({
            'name': media.get('filename') or 'file', 'raw': raw,
            'mimetype': media.get('mimetype') or 'application/octet-stream'})

    def _process_incoming(self, items):
        self.ensure_one()
        Message, Chat = self.env['whatsapp.message'].sudo(), self.env['whatsapp.chat'].sudo()
        created = 0
        for item in items:
            mid = item.get('message_id')
            if not mid or Message.search_count([('account_id', '=', self.id), ('message_id', '=', mid)]):
                continue        # already known (also our own sends echoed back)
            chat = Chat.search([('account_id', '=', self.id), ('phone', '=', item['phone'])], limit=1)
            if not chat:
                continue        # never store chats Odoo did not start
            # typed on the phone: an outgoing message - unless it is the chat with the
            # linked number itself ("message yourself"), the only way to reply there
            own = ''.join(c for c in (self.phone or '') if c.isdigit())[-10:]
            outgoing = bool(item.get('from_me')) and not (own and chat.phone.endswith(own))
            if item.get('name') and not chat.contact_name and not outgoing:
                chat.contact_name = item['name']
            date = datetime.fromtimestamp(item.get('timestamp') or 0, timezone.utc).replace(tzinfo=None)
            attachment = self._store_media(item.get('media'))
            message = Message.create({
                'attachment_id': attachment.id, 'account_id': self.id, 'chat_id': chat.id, 'phone': item['phone'],
                'direction': 'out' if outgoing else 'in',
                'status': 'SENT' if outgoing else 'RECEIVED', 'is_read': outgoing, 'message_id': mid,
                'body': item.get('body') or False, 'media_type': item.get('media_type') or False,
                'date': date, 'user_id': False,
            })
            if not outgoing:
                self._notify_users(chat, message)
            if attachment:      # readable by whoever can read the message
                attachment.write({'res_model': 'whatsapp.message', 'res_id': message.id})
            created += 1
        return created
