#!/usr/bin/env python3
"""Short-lived WhatsApp helper process spawned by the ``whatsapp_qr_connect``
Odoo module.

Odoo workers are recycled at any time, so no WhatsApp connection is ever kept
inside an Odoo process.  Instead, every link / send / check / logout operation
runs this script in its own process.  It

* reads its instructions from the ``WA_WORKER_CONFIG`` environment variable
  (JSON, never from the command line so nothing leaks into ``ps``),
* restores the WhatsApp session of one ``whatsapp.account`` from the Odoo
  database (column ``session_data``, a sqlite file),
* talks to WhatsApp through ``neonize`` (Python bindings of the maintained
  ``whatsmeow`` library),
* writes the result back into the ``whatsapp_account`` table and prints a final
  JSON line on stdout for the caller.

It deliberately does not import Odoo.
"""
import json
import os
import signal
import sqlite3
import sys
import tempfile
import threading
import time
import traceback
import types

LINK_TIMEOUT = 170          # seconds a QR code can be scanned
CONNECT_TIMEOUT = 30        # seconds to (re)connect an existing session
SETTLE_AFTER_PAIR = 6       # seconds to let WhatsApp finish the first sync


def log(*args):
    print(*args, file=sys.stderr, flush=True)


def finish(payload, code=0):
    """Print the result line and hard-exit.

    neonize keeps non-daemon threads alive, so a normal interpreter exit can
    hang; ``os._exit`` guarantees the process ends.
    """
    try:
        text = json.dumps(payload)
    except TypeError:
        log('cannot serialise result: %r' % (payload,))
        text = json.dumps(payload, default=str)
    print(text, flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


# --------------------------------------------------------------------------
# Environment helpers
# --------------------------------------------------------------------------
def stub_magic():
    """neonize imports ``python-magic`` (needs the libmagic system library).
    It is only used for media, so fall back to a stub when it is unavailable
    (e.g. on Odoo.sh)."""
    try:
        import magic  # noqa: F401
    except Exception:
        fake = types.ModuleType('magic')
        fake.from_buffer = lambda *a, **k: 'application/octet-stream'
        fake.from_file = lambda *a, **k: 'application/octet-stream'

        class _Magic:
            def __init__(self, *a, **k):
                pass

            from_buffer = staticmethod(fake.from_buffer)
            from_file = staticmethod(fake.from_file)

        fake.Magic = _Magic
        sys.modules['magic'] = fake


class Db:
    """Minimal accessor for the one ``whatsapp_account`` row we work on."""

    def __init__(self, cfg):
        import psycopg2
        self.psycopg2 = psycopg2
        self.conn = psycopg2.connect(**cfg['db']['params'])
        self.conn.autocommit = True
        self.account_id = cfg['account_id']

    def update(self, **vals):
        if not vals:
            return
        cols = ', '.join('%s = %%s' % k for k in vals)
        with self.conn.cursor() as cur:
            cur.execute(
                'UPDATE whatsapp_account SET %s WHERE id = %%s' % cols,
                [*vals.values(), self.account_id],
            )

    def stop_requested(self):
        with self.conn.cursor() as cur:
            cur.execute('SELECT listen_stop FROM whatsapp_account WHERE id = %s', [self.account_id])
            row = cur.fetchone()
        return bool(row and row[0])

    def get_session(self):
        with self.conn.cursor() as cur:
            cur.execute('SELECT session_data FROM whatsapp_account WHERE id = %s',
                        [self.account_id])
            row = cur.fetchone()
        return bytes(row[0]) if row and row[0] else None

    def save_session(self, blob, **extra):
        self.update(session_data=self.psycopg2.Binary(blob), **extra)


def snapshot(path):
    """Consistent single-file copy of the live sqlite session (merges the WAL)."""
    last_error = None
    for _attempt in range(5):
        fd, tmp = tempfile.mkstemp(suffix='.sqlite3')
        os.close(fd)
        try:
            src = sqlite3.connect(path, timeout=10)
            dst = sqlite3.connect(tmp)
            with dst:
                src.backup(dst)
            dst.close()
            src.close()
            with open(tmp, 'rb') as fh:
                return fh.read()
        except sqlite3.Error as exc:
            last_error = exc
            time.sleep(0.5)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    raise RuntimeError('Could not snapshot the WhatsApp session: %s' % last_error)


class Session:
    """A neonize client bound to a sqlite file, with the events we care about."""

    def __init__(self, db, workdir, fresh=False):
        stub_magic()
        from neonize.client import NewClient
        from neonize.events import (
            ConnectedEv, ConnectFailureEv, LoggedOutEv, PairStatusEv,
            StreamReplacedEv,
        )
        self.db = db
        self.path = os.path.join(workdir, 'session.sqlite3')
        if not fresh:
            blob = db.get_session()
            if blob:
                with open(self.path, 'wb') as fh:
                    fh.write(blob)
        self.had_session = os.path.exists(self.path)
        self.state = {}
        self.client = NewClient(name=self.path, new_device=fresh)
        st = self.state

        @self.client.qr
        def _on_qr(_client, data):
            st['qr'] = data.decode() if isinstance(data, bytes) else str(data)
            st['qr_seen'] = True
            if st.get('on_qr'):
                st['on_qr'](st['qr'])

        @self.client.event(PairStatusEv)
        def _on_pair(_client, ev):
            st['paired'] = ev

        @self.client.event(ConnectedEv)
        def _on_connected(_client, _ev):
            st['connected_ev'] = True

        @self.client.event(LoggedOutEv)
        def _on_logged_out(_client, ev):
            st['logged_out'] = getattr(ev, 'Reason', 0) or True

        @self.client.event(ConnectFailureEv)
        def _on_failure(_client, ev):
            st['failure'] = '%s %s' % (getattr(ev, 'Reason', ''), getattr(ev, 'Message', ''))

        @self.client.event(StreamReplacedEv)
        def _on_replaced(_client, _ev):
            st['replaced'] = True

    def start(self):
        def _run():
            try:
                self.client.connect()
            except BaseException as exc:  # noqa: BLE001
                self.state['error'] = '%s: %s' % (type(exc).__name__, exc)
        threading.Thread(target=_run, daemon=True, name='neonize-connect').start()

    def is_up(self):
        try:
            return bool(self.client.is_connected and self.client.is_logged_in)
        except Exception:  # noqa: BLE001 - Go side not ready yet
            return False

    def wait_connected(self, timeout):
        """Returns 'OK', 'NOT_LINKED', 'LOGGED_OUT', 'REPLACED' or 'TIMEOUT:<why>'."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = self.state
            if st.get('logged_out'):
                return 'LOGGED_OUT'
            if st.get('qr_seen') and not self.had_session:
                return 'NOT_LINKED'
            if st.get('qr_seen'):
                # A stored session that is asking for a QR is no longer valid.
                return 'NOT_LINKED'
            if st.get('replaced'):
                return 'REPLACED'
            if st.get('error'):
                return 'TIMEOUT:%s' % st['error']
            if st.get('failure'):
                return 'TIMEOUT:%s' % st['failure']
            if self.is_up():
                return 'OK'
            time.sleep(0.3)
        return 'TIMEOUT:not connected within %ss' % timeout

    def persist(self, **extra):
        self.db.save_session(snapshot(self.path), **extra)


# --------------------------------------------------------------------------
# Modes
# --------------------------------------------------------------------------
def mode_link(cfg, db, workdir):
    session = Session(db, workdir, fresh=True)
    st = session.state
    db.update(state='linking', qr_string=None, last_error=None,
              link_pid=os.getpid())

    def on_qr(qr):
        db.update(qr_string=qr)
    st['on_qr'] = on_qr
    session.start()

    deadline = time.time() + (cfg.get('timeout') or LINK_TIMEOUT)
    while time.time() < deadline and 'paired' not in st:
        if st.get('error'):
            break
        time.sleep(0.5)

    if 'paired' not in st:
        reason = st.get('error') or 'The QR code was not scanned in time.'
        db.update(state='draft', qr_string=None, link_pid=None, last_error=reason)
        finish({'ok': False, 'error': reason})

    # Paired: WhatsApp now drops and re-establishes the connection.
    db.update(qr_string=None)
    end = time.time() + 40
    while time.time() < end and not session.is_up():
        time.sleep(0.5)
    if not session.is_up():
        reason = 'Linked, but the connection could not be re-established.'
        db.update(state='draft', link_pid=None, last_error=reason)
        finish({'ok': False, 'error': reason})

    time.sleep(SETTLE_AFTER_PAIR)
    phone, push_name = None, None
    try:
        me = session.client.get_me()
        phone = me.JID.User
        push_name = me.PushName
    except Exception:  # noqa: BLE001
        paired = st['paired']
        try:
            phone = paired.ID.User
        except Exception:  # noqa: BLE001
            pass
    session.persist(
        state='connected', phone=phone or None, push_name=push_name or None,
        qr_string=None, last_error=None, link_pid=None,
        last_connected=time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()),
    )
    finish({'ok': True, 'phone': phone, 'push_name': push_name})


def _connect_existing(cfg, db, workdir, before_start=None):
    session = Session(db, workdir)
    if not session.had_session:
        db.update(state='draft')
        finish({'ok': False, 'code': 'NOT_LINKED',
                'error': 'This WhatsApp number is not linked.'})
    if before_start:
        before_start(session)       # e.g. message handlers: queued messages arrive on connect
    session.start()
    result = session.wait_connected(cfg.get('connect_timeout') or CONNECT_TIMEOUT)
    if result in ('NOT_LINKED', 'LOGGED_OUT'):
        db.update(state='disconnected', last_error='WhatsApp logged this device out. '
                  'Please link the number again.', session_data=None)
        finish({'ok': False, 'code': 'NOT_LINKED',
                'error': 'The WhatsApp session is no longer valid. Link the number again.'})
    if result != 'OK':
        finish({'ok': False, 'code': 'CONNECT_FAILED', 'error': result})
    return session


def mode_send(cfg, db, workdir):
    register, incoming = make_collector(cfg)
    session = _connect_existing(cfg, db, workdir, before_start=register)
    client = session.client
    from neonize.utils import build_jid
    results = []
    for msg in cfg['payload']['messages']:
        number = msg['to']
        try:
            jid = None
            try:
                found = client.is_on_whatsapp('+' + number)
            except Exception as exc:  # noqa: BLE001
                log('is_on_whatsapp failed: %s' % exc)
                found = []
            if found:
                if not found[0].IsIn:
                    results.append({'status': 'NOT_WHATSAPP'})
                    continue
                jid = found[0].JID
            if jid is None:
                jid = build_jid(number)
            att = msg.get('attachment')
            mime = (att or {}).get('mimetype') or ''
            if att and att.get('as_media') and mime.startswith('image/'):
                resp = client.send_image(jid, att['path'], caption=msg.get('text') or None)
            elif att and att.get('as_media') and mime.startswith('video/'):
                resp = client.send_video(jid, att['path'], caption=msg.get('text') or None)
            elif att and att.get('as_media') and mime.startswith('audio/'):
                resp = client.send_audio(jid, att['path'])
            elif att:
                resp = client.send_document(
                    jid, att['path'], caption=msg.get('text') or None,
                    filename=att.get('filename'),
                    mimetype=att.get('mimetype') or 'application/pdf')
            else:
                resp = client.send_message(jid, msg['text'])
            results.append({'status': 'SENT', 'message_id': getattr(resp, 'ID', '')})
        except Exception as exc:  # noqa: BLE001
            log(traceback.format_exc())
            results.append({'status': 'ERROR', 'detail': '%s: %s' % (type(exc).__name__, exc)})
    time.sleep(1)  # let the last ack / key updates settle before snapshotting
    try:
        session.persist(last_connected=time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()))
    except Exception:  # noqa: BLE001
        log(traceback.format_exc())
    finish({'ok': True, 'results': results, 'messages': incoming})


def mode_check(cfg, db, workdir):
    session = _connect_existing(cfg, db, workdir)
    phone = None
    try:
        phone = session.client.get_me().JID.User
    except Exception:  # noqa: BLE001
        pass
    session.persist(state='connected', last_error=None,
                    last_connected=time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()))
    finish({'ok': True, 'phone': phone})


MAX_MEDIA_BYTES = 16 * 1024 * 1024


def _download_media(client, msg, sub, message_id, media_dir):
    """Save the attachment into ``media_dir``; None when it is too big or fails."""
    if not media_dir:
        return None
    import mimetypes
    import re
    size = int(getattr(sub, 'fileLength', 0) or 0)
    if size > MAX_MEDIA_BYTES:
        return None
    try:
        data = client.download_any(msg)
    except Exception:  # noqa: BLE001
        log(traceback.format_exc())
        return None
    if not data or len(data) > MAX_MEDIA_BYTES:
        return None
    mime = (getattr(sub, 'mimetype', '') or 'application/octet-stream').split(';')[0]
    name = getattr(sub, 'fileName', '') or ''
    if not name:
        name = 'whatsapp-%s%s' % (message_id, mimetypes.guess_extension(mime) or '')
    path = os.path.join(media_dir, re.sub(r'[^\w.\-]+', '_', message_id))
    with open(path, 'wb') as fh:
        fh.write(data)
    return {'path': path, 'mimetype': mime, 'filename': name}


def _match_known(user, known):
    """Odoo may store a number as 0301..., WhatsApp reports 92301...: compare the
    last 10 digits and hand back the number as Odoo knows it."""
    digits = ''.join(c for c in user if c.isdigit())
    if len(digits) < 8:
        return None
    for number in known:
        other = ''.join(c for c in number if c.isdigit())
        if other and (other == digits or (len(other) >= 10 and len(digits) >= 10
                                          and other[-10:] == digits[-10:])):
            return number
    return None


def _incoming_from_event(client, ev, known, media_dir=None):
    """Turn a neonize MessageEv into a plain dict, or None when it is not a
    1:1 message from a number that Odoo has already written to."""
    info = ev.Info
    src = info.MessageSource
    if src.IsGroup:
        return None
    # messages typed on the phone itself (IsFromMe) belong to the chat with the *recipient*
    jids = (src.Chat, getattr(src, 'RecipientAlt', None)) if src.IsFromMe \
        else (src.SenderAlt, src.Sender, src.Chat)
    phone = None
    for jid in jids:
        user = getattr(jid, 'User', '') or ''
        if user and getattr(jid, 'Server', '') == 'lid':
            try:
                user = client.get_pn_from_lid(jid).User or ''
            except Exception:  # noqa: BLE001
                user = ''
        phone = _match_known(user, known)
        if phone:
            break
    if not phone:
        return None
    msg = ev.Message
    body, media, media_file = '', '', None
    if msg.conversation:
        body = msg.conversation
    elif msg.HasField('extendedTextMessage'):
        body = msg.extendedTextMessage.text
    else:
        for field, label in (('imageMessage', 'image'), ('videoMessage', 'video'),
                             ('documentMessage', 'document'), ('audioMessage', 'audio'),
                             ('stickerMessage', 'sticker'), ('locationMessage', 'location'),
                             ('contactMessage', 'contact')):
            if msg.HasField(field):
                media = label
                sub = getattr(msg, field)
                body = getattr(sub, 'caption', '') or ''
                media_file = _download_media(client, msg, sub, ev.Info.ID, media_dir)
                break
        else:
            return None       # reactions, protocol messages, receipts ...
    ts = int(info.Timestamp or 0)
    if ts > 10 ** 11:
        ts //= 1000
    return {'phone': phone, 'from_me': bool(src.IsFromMe), 'name': info.Pushname or '', 'message_id': info.ID,
            'body': body, 'media_type': media, 'media': media_file, 'timestamp': ts or int(time.time())}


def make_collector(cfg, emit=None):
    """Returns (register, found): ``register(session)`` hooks the message handler
    (must run BEFORE connecting, queued messages arrive on connect)."""
    from neonize.events import MessageEv
    payload = cfg.get('payload') or {}
    known = list(payload.get('known') or [])
    found, seen = [], set()

    def register(session):
        @session.client.event(MessageEv)
        def _on_message(client, ev):
            try:
                item = _incoming_from_event(client, ev, known, payload.get('media_dir'))
            except Exception:  # noqa: BLE001
                log(traceback.format_exc())
                return
            if not item:
                src = ev.Info.MessageSource
                log('receive: ignored message (group=%s, from_me=%s, chat=%s, sender=%s)' % (
                    src.IsGroup, src.IsFromMe, src.Chat.User, src.Sender.User))
            elif item['message_id'] not in seen:
                log('receive: got message %s (from_me=%s)' % (item['message_id'], item['from_me']))
                seen.add(item['message_id'])
                found.append(item)
                if emit:
                    emit(item)
    return register, found


def mode_receive(cfg, db, workdir):
    """Stay connected for ``window`` seconds and hand every message for numbers Odoo
    talked to to Odoo the moment it arrives (one ``MSG <json>`` line each).
    Ends early when Odoo wants the session for a send (``listen_stop`` flag)."""
    def emit(item):
        print('MSG ' + json.dumps(item), flush=True)

    register, found = make_collector(cfg, emit)
    session = _connect_existing(cfg, db, workdir, before_start=register)
    end = time.time() + (cfg['payload'].get('window') or 12)
    while time.time() < end:
        try:
            if db.stop_requested():
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)
    time.sleep(1)
    try:
        session.persist(last_connected=time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()))
    except Exception:  # noqa: BLE001
        log(traceback.format_exc())
    finish({'ok': True, 'count': len(found)})


def mode_logout(cfg, db, workdir):
    error = None
    try:
        session = Session(db, workdir)
        if session.had_session:
            session.start()
            if session.wait_connected(cfg.get('connect_timeout') or CONNECT_TIMEOUT) == 'OK':
                session.client.logout()
            else:
                error = 'Could not reach WhatsApp; the device was only removed from Odoo.'
    except Exception as exc:  # noqa: BLE001
        error = '%s: %s' % (type(exc).__name__, exc)
    db.update(state='draft', session_data=None, qr_string=None, link_pid=None,
              last_error=error)
    finish({'ok': True, 'warning': error})


MODES = {
    'link': mode_link,
    'send': mode_send,
    'check': mode_check,
    'receive': mode_receive,
    'logout': mode_logout,
}


def main():
    try:
        cfg = json.loads(os.environ['WA_WORKER_CONFIG'])
    except Exception as exc:  # noqa: BLE001
        finish({'ok': False, 'error': 'Bad worker configuration: %s' % exc}, 2)

    signal.signal(signal.SIGTERM, lambda *_a: os._exit(143))
    workdir = tempfile.mkdtemp(prefix='wa_worker_')
    os.chdir(workdir)
    db = None
    try:
        db = Db(cfg)
        try:
            import neonize  # noqa: F401
        except Exception:  # noqa: BLE001
            stub_magic()
            import neonize  # noqa: F401
        MODES[cfg['mode']](cfg, db, workdir)
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001
        text = '%s: %s' % (type(exc).__name__, exc)
        log(traceback.format_exc())
        if db is not None and cfg.get('mode') == 'link':
            try:
                db.update(state='draft', qr_string=None, link_pid=None, last_error=text)
            except Exception:  # noqa: BLE001
                pass
        finish({'ok': False, 'error': text}, 1)


if __name__ == '__main__':
    main()
