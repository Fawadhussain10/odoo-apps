# PDC Cheque Management

Post-dated cheque management for Odoo 20.

Register customer and vendor post-dated cheques from invoices and bills, then move them through
Registered, Deposited, Cleared, Returned, Bounced and Cancelled. The journal entries are posted for you.

## Features

- Its own **PDC Cheques** app: Customer Cheques, Vendor Cheques, All Cheques
- List, kanban, form, due calendar, pivot and graph views
- Smart buttons for invoices, journal entries, journal items and attachments, plus partner and invoice links
- Bulk register, deposit and clear actions
- Due-date email reminders for customers, vendors and internal users
- Reports: PDC Cheque Voucher, PDC Cheque Register, PDC Cheque Report (filter by partners and status)

## Accounting

While a cheque is pending it is held in the PDC accounts chosen in Settings: PDC Receivable for
customer cheques and PDC Payable for vendor cheques.

| Step | Customer cheque | Vendor cheque |
|------|-----------------|---------------|
| Deposit | Dr PDC Receivable / Cr Receivable | Dr Payable / Cr PDC Payable |
| Bounce | reverses the deposit | reverses the deposit |
| Clear | Dr Bank / Cr PDC Receivable | Dr PDC Payable / Cr Bank |

## Configuration

PDC Cheques > Configuration > Settings: set the PDC accounts for customers and vendors, due-date
reminders, auto-fill of open invoices and cancel options.

## Support

PackBytes | https://www.packbytes.com | sales@packbytes.com
