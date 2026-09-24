# WhatsApp QR Connect (Odoo 19)

Link WhatsApp numbers by scanning a QR code **inside Odoo** and send messages
from any other module. No Node.js / gateway service.

## Install
1. Install the Python library **neonize==0.5.2** in the environment Odoo runs in:
   `pip install neonize==0.5.2` (it is also listed in the repository's `requirements.txt`).
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
