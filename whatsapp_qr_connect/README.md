# WhatsApp QR Connect (Odoo 20)

Link WhatsApp numbers by scanning a QR code **inside Odoo** and send messages
from any other module. No Node.js / gateway service.

## Install
1. Install the Python library **neonize==0.5.2** (it needs `protobuf>=7.34.1`) where Odoo runs:
   `pip install neonize==0.5.2` (also listed in the repository's `requirements.txt` on Odoo.sh).
   *If your Odoo Python pins an older protobuf* (for example Firebase / Google Cloud libraries need
   `protobuf<7`), install it in a **separate virtualenv** instead:
   `python -m venv /opt/whatsapp-venv && /opt/whatsapp-venv/bin/pip install neonize==0.5.2 psycopg2-binary`
   and set the system parameter `whatsapp_qr_connect.python_path` to `/opt/whatsapp-venv/bin/python`.
2. Install the module. Go to **Settings > Technical > WhatsApp > WhatsApp Numbers**
   (needs developer mode). While nothing is linked this opens the QR screen directly.
3. On the phone: WhatsApp > Linked devices > Link a device > scan.

More numbers: **Link New Number** on the list. Each number has its own session.

## WhatsApp buttons on your documents
Once a number is linked, these forms get a **WhatsApp** button (only for the apps that are installed):

| Form | Sends |
|------|-------|
| Sales Order / Quotation | order PDF |
| Purchase Order / RFQ | order PDF |
| Inventory transfer (delivery / receipt) | delivery slip PDF |
| Customer Invoice, Credit Note, Vendor Bill, Refund (posted) | invoice PDF |
| Salary Slip (needs Payroll) | payslip PDF |
| Contact | customer / vendor ledger PDF (built-in report, no Enterprise needed) |

The button opens a dialog: choose the sending number, check the phone, edit the message, and
keep **Attach PDF** ticked to send the document as a file (untick for text only).

## Use from other modules
```python
Account = self.env['whatsapp.account']

# 1. Fire and forget (uses the default / only linked number)
res = Account.send_message('923001234567', 'Hello!', res_model='sale.order', res_id=self.id)
# res['status']: SENT | NOT_WHATSAPP | INVALID_PHONE | NOT_LINKED | ERROR

# 2. Specific number
Account.send_message(phone, text, account=some_account_record)

# 3. Many messages over ONE connection (crons, bulk)
Account.send_messages([{'phone': p, 'message': m} for p, m in pairs])

# 4. From a button: asks "Send from which number?" when more than one is linked,
#    otherwise sends immediately and shows a notification.
return Account.action_send_message(phone, text, res_model=self._name, res_id=self.id)
```
Every message is logged under **WhatsApp > Message Log**, including the attached file name.

`send_message(..., attachment={'filename': 'Invoice.pdf', 'content': pdf_bytes, 'mimetype': 'application/pdf'})` sends a file.

## Settings (System Parameters)
* `whatsapp_qr_connect.default_country_code` - e.g. `92`; lets `0300...` local numbers work.
* `whatsapp_qr_connect.python_path` - interpreter that has `neonize` (default: Odoo's own).

## How it works
Odoo never keeps a WhatsApp connection open. Each link / send / check runs
`worker/whatsapp_worker.py` as a short-lived subprocess. The login of each number is
stored in the database (`session_data`) so it survives restarts and works on Odoo.sh.
Sends to one number are serialised with a PostgreSQL advisory lock.

## Notes
* Uses the unofficial WhatsApp Web protocol (via `neonize` / whatsmeow). Use it with
  your own numbers and expect WhatsApp to enforce its terms; the official Cloud API is
  the only officially supported route.
* Anyone with database access can read the stored sessions: treat backups like passwords.
* Media messages need `ffmpeg`; plain text does not.


## WhatsApp app: chats and replies inside Odoo

A **WhatsApp** app icon appears on the Odoo home screen. It lists only the
conversations that Odoo started (a chat is created when a message is sent to a
number from Odoo - other chats on the linked phone are never read into Odoo).

* Replies from those numbers are stored and shown as chat bubbles; you can answer from the screen.
* A short pop-up ("New WhatsApp message from ...", 2 seconds, with an *Open* button)
  appears on any Odoo screen when a reply arrives.
* **Access:** only members of the group *WhatsApp / Chat User* see the app, can read the chats and
  get the pop-up (administrators are members automatically). Add the group on the user form.
* **Speed:** a scheduled action (*WhatsApp: fetch new replies*, every minute) keeps one WhatsApp
  connection open for about 50 seconds per run, so replies are stored the moment WhatsApp delivers
  them and pushed to the browser over Odoo's bus websocket (pop-up within a second or two). The
  listener steps aside automatically when you send a message. It uses one Odoo cron thread; keep
  the cron enabled (`--max-cron-threads` >= 1). *Check now* does a short manual run.
* **Composer:** emoji picker, file button (also paste or drop pictures) - pictures, videos, audio, PDFs
  and any other file up to 16 MB; the text becomes the caption.
* Received media (images, stickers, videos, voice notes, documents up to 16 MB) is downloaded and stored as an attachment; images are shown inline, other files as players or download links.
