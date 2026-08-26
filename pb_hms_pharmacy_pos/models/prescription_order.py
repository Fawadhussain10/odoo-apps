# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class PrescriptionOrder(models.Model):
    _inherit = ['prescription.order', 'pos.load.mixin']

    pos_order_line_ids = fields.One2many('pos.order.line', 'prescription_order_origin_id', string="Order lines Transfered to Point of Sale", readonly=True, groups="point_of_sale.group_pos_user")
    pos_order_count = fields.Integer(string='Pos Order Count', compute='_count_pos_order', readonly=True, groups="point_of_sale.group_pos_user")
    fiscal_position_id = fields.Many2one('account.fiscal.position', string='Fiscal Position', readonly=True)
    partner_id = fields.Many2one(related='patient_id.partner_id', string='Customer', store=True)
    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist')
    date_order = fields.Datetime(related='prescription_date', store=True, string="Order Date")
    deliver_only_once = fields.Boolean("Deliver only Once", default=True)
    pb_pos_processed = fields.Boolean(compute="_check_pb_pos_processed", store=True)

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        return super(PrescriptionOrder, self).search_read(domain, fields, offset, limit, order)

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [('pos_order_line_ids.order_id.state', '=', 'draft')]

    @api.model
    def _load_pos_data_fields(self, config):
        return ['name', 'state', 'patient_id', 'physician_id', 'prescription_date', 'partner_id',
            'pricelist_id', 'fiscal_position_id', 'amount_total', 'amount_untaxed',
            'pb_pos_processed', 'pos_order_count', 'currency_id']

    def load_prescription_order_from_pos(self, config_id):
        product_ids = self.prescription_line_ids.product_id.ids
        product_tmpls = self.env['product.template'].with_context(load_archived=True).load_product_from_pos(
            config_id,
            [('product_variant_ids.id', 'in', product_ids)]
        )
        prescription_order_fields = self._load_pos_data_fields(config_id)
        prescription_order_read = self.read(prescription_order_fields, load=False)
        prescription_line_fields = self.prescription_line_ids._load_pos_data_fields(config_id)
        prescription_line_read = self.prescription_line_ids.read(prescription_line_fields, load=False)
        prescription_order_fp_fields = self.env['account.fiscal.position']._load_pos_data_fields(config_id)
        prescription_order_fp_read = self.fiscal_position_id.read(prescription_order_fp_fields, load=False)
        partner_fields = self.env['res.partner']._load_pos_data_fields(config_id)

        return {
            'prescription.order': prescription_order_read,
            'prescription.line': prescription_line_read,
            'account.fiscal.position': prescription_order_fp_read,
            'res.partner': self.partner_id.read(partner_fields, load=False),
            **product_tmpls,
        }

    @api.depends('deliver_only_once','pos_order_line_ids')
    def _check_pb_pos_processed(self):
        for rec in self:
            rec.pb_pos_processed = True if (rec.deliver_only_once and rec.pos_order_line_ids) else False

    def _count_pos_order(self):
        for order in self:
            linked_orders = order.pos_order_line_ids.mapped('order_id')
            order.pos_order_count = len(linked_orders)

    def action_view_pos_order(self):
        self.ensure_one()
        linked_orders = self.pos_order_line_ids.mapped('order_id')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Linked POS Orders'),
            'res_model': 'pos.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', linked_orders.ids)],
        }

class PrescriptionLine(models.Model):
    _inherit = ['prescription.line', 'pos.load.mixin']

    pos_order_line_ids = fields.One2many('pos.order.line', 'prescription_order_line_id', string="Order lines Transfered to Point of Sale", readonly=True, groups="point_of_sale.group_pos_user")
    qty_delivered = fields.Float(compute="_compute_qty_delivered", store=True)
    qty_invoiced = fields.Float(compute="_compute_qty_invoiced", store=True)

    #PB: fields added with needed name on pos order for more simplicity
    product_uom_qty = fields.Float(related='quantity', store=True, string='Quantity for POS')
    product_uom = fields.Many2one(related="dosage_uom_id", store=True, string='UOM for POS')
    order_id = fields.Many2one(related='prescription_id', store=True, string='Prescription for POS')
    is_kit_product = fields.Boolean(related='product_id.is_kit_product', store=True)

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [('order_id', 'in', [order['id'] for order in data['prescription.order']])]

    @api.model
    def _load_pos_data_fields(self, config):
        return ['product_id', 'name', 'price_unit', 'product_uom_qty', 'product_uom', 'tax_ids',
            'price_total', 'qty_delivered', 'qty_invoiced', 'discount', 'is_kit_product',
            'display_type', 'order_id']

    @api.depends('pos_order_line_ids.qty')
    def _compute_qty_delivered(self):
        for prescription_line in self:
            prescription_line.qty_delivered += sum([self._convert_qty(prescription_line, pos_line.qty, 'p2s') for pos_line in prescription_line.pos_order_line_ids if prescription_line.product_id.type != 'service'], 0)

    @api.depends('pos_order_line_ids.qty')
    def _compute_qty_invoiced(self):
        for prescription_line in self:
            prescription_line.qty_invoiced += sum([self._convert_qty(prescription_line, pos_line.qty, 'p2s') for pos_line in prescription_line.pos_order_line_ids], 0)

    def read_converted(self):
        field_names = [ "product_id", "name", "price_unit", "product_uom_qty", "tax_ids", "price_total", "qty_delivered", "qty_invoiced", "discount", "is_kit_product"] #"qty_to_invoice"
        results = []
        for prescription_line in self:
            if prescription_line.product_id and prescription_line.product_id.type!='service':
                product_uom = prescription_line.product_id.uom_id
                prescription_line_uom = prescription_line.product_id.uom_id
                item = prescription_line.read(field_names)[0]
                if prescription_line.product_id.tracking != 'none':
                    item['lot_names'] = prescription_line.move_ids.move_line_ids.lot_id.mapped('name')
                # if product_uom == prescription_line_uom:
                #     results.append(item)
                #     continue
                item['product_uom_qty'] = self._convert_qty(prescription_line, item['product_uom_qty'], 's2p')
                item['qty_delivered'] = self._convert_qty(prescription_line, item['qty_delivered'], 's2p')
                item['qty_invoiced'] = self._convert_qty(prescription_line, item['qty_invoiced'], 's2p')
                # item['qty_to_invoice'] = self._convert_qty(prescription_line, item['qty_to_invoice'], 's2p')
                item['price_unit'] = prescription_line_uom._compute_price(item['price_unit'], product_uom)

                #Manage kit product also
                if not prescription_line.product_id.is_kit_product:
                    results.append(item)
                else:
                    for kit_line in prescription_line.product_id.pb_kit_line_ids:
                        if kit_line.product_id.type!='service':
                            qty = kit_line.product_qty * prescription_line.product_uom_qty
                            item = {
                                'id': prescription_line.id,
                                'product_id': (kit_line.product_id.id, kit_line.product_id.display_name),
                                'product_uom_qty': qty,
                                'price_unit': kit_line.product_id.list_price,
                                'name': kit_line.product_id.name,
                                'tax_ids': [],
                                'price_total': qty * kit_line.product_id.list_price,
                                'qty_delivered': 0,
                                'qty_invoiced': 0,
                                'discount': 0,
                                'is_kit_product': True,
                                'kit_product_name': prescription_line.product_id.name,
                                'kit_product_qty': prescription_line.product_uom_qty,
                                'product_uom_id': kit_line.product_id.uom_id.id,
                                'lot_names': []
                            }
                            results.append(item)
            elif prescription_line.display_type == 'line_note':
                if results:
                    results[-1]['customer_note'] = prescription_line.name
        return results

    @api.model
    def _convert_qty(self, prescription_line, qty, direction):
        """Converts the given QTY based on the given SALE_LINE and DIR.

        if DIR='s2p': convert from prescription line uom to product uom
        if DIR='p2s': convert from product uom to prescription line uom
        """
        product_uom = prescription_line.product_id.uom_id
        prescription_line_uom = prescription_line.product_uom
        if direction == 's2p':
            return prescription_line_uom._compute_quantity(qty, product_uom, False)
        elif direction == 'p2s':
            return product_uom._compute_quantity(qty, prescription_line_uom, False)

