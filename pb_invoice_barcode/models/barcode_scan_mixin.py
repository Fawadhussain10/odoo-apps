# -*- encoding: utf-8 -*-

from odoo import api, fields, models


class BarcodeScanMixin(models.AbstractModel):
    """ Replacement for the barcodes.barcode_events_mixin removed in Odoo 20.

    Forms add `<field name="_barcode_scanned" widget="pb_invoice_barcode_handler"/>`; the widget
    writes each scanned barcode into the field, which triggers
    `on_barcode_scanned` through the onchange below.
    """
    _name = 'pb.invoice.barcode.scan.mixin'
    _description = 'Barcode Scan Mixin'

    _barcode_scanned = fields.Char("Barcode Scanned", store=False,
        help="Value of the last barcode scanned.")

    @api.onchange('_barcode_scanned')
    def _on_barcode_scanned(self):
        barcode = self._barcode_scanned
        if barcode:
            self._barcode_scanned = ""
            return self.on_barcode_scanned(barcode)

    def on_barcode_scanned(self, barcode):
        raise NotImplementedError("Implement on_barcode_scanned() in models using this mixin.")
