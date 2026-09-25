from odoo import api, fields, models

DISPLAY_TYPE_SELECTION = [
    ("section", "Section"),
    ("subtotal", "Subtotal"),
]

FORMULA_TYPE_SELECTION = [
    ("manual", "Manual Quantity"),
    ("dimensional", "Dimensional (Number x L x W x H)"),
]


class ConstructionBoqLineMixin(models.AbstractModel):
    """Shared measurement/costing fields and formulas for BOQ template lines and project BOQ
    lines (FDD 5.2/5.3): Gross = Number x L x W x H, Net = Gross - Deductions,
    Procurement Qty = Net x (1 + Waste %), Amount = Net Qty x Rate. Section/subtotal rows are
    display groupings, not purchasable quantities."""

    _name = "construction.boq.line.mixin"
    _description = "Construction BOQ Line (shared fields)"

    sequence = fields.Integer(default=10)
    display_type = fields.Selection(DISPLAY_TYPE_SELECTION, default=False)
    name = fields.Char(string="Item / Description", required=True)
    technical_basis = fields.Text(string="Technical Quantity Basis")
    source_remarks = fields.Char(string="Source / Remarks")

    cost_code_id = fields.Many2one("construction.cost.code", string="Cost Code")
    work_type_id = fields.Many2one("construction.work.type", string="Trade / Work Type")
    product_id = fields.Many2one("product.product", string="Product")
    product_category_id = fields.Many2one("product.category", string="Product Category",
                                           help="Used when the item is budgeted at category level (e.g. Cement) rather than an exact product.")
    uom_id = fields.Many2one("uom.uom", string="UoM")

    formula_type = fields.Selection(FORMULA_TYPE_SELECTION, default="manual")
    number = fields.Float(string="Number", default=1.0)
    length = fields.Float(string="Length")
    width = fields.Float(string="Width")
    height = fields.Float(string="Height")
    deduction = fields.Float(string="Deductions")
    gross_qty = fields.Float(string="Gross Qty", compute="_compute_quantities", store=True)
    waste_pct = fields.Float(string="Waste %", default=0.0)
    net_qty = fields.Float(string="Net Qty", compute="_compute_quantities", store=True)
    procurement_qty = fields.Float(string="Procurement Qty", compute="_compute_quantities", store=True,
                                    help="Net Qty x (1 + Waste %) - the quantity to actually procure.")

    rate = fields.Float(string="Budget Rate")
    customer_rate = fields.Float(string="Customer Rate")
    amount = fields.Monetary(string="Amount", compute="_compute_amount", store=True, currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", compute="_compute_currency_id")

    @api.depends("number", "length", "width", "height", "deduction", "formula_type", "waste_pct")
    def _compute_quantities(self):
        for rec in self:
            if rec.display_type:
                rec.gross_qty = rec.net_qty = rec.procurement_qty = 0.0
                continue
            if rec.formula_type == "dimensional":
                factors = [f for f in (rec.length, rec.width, rec.height) if f]
                gross = rec.number or 1.0
                for f in factors:
                    gross *= f
            else:
                gross = rec.number
            rec.gross_qty = gross
            rec.net_qty = gross - rec.deduction
            rec.procurement_qty = rec.net_qty * (1 + (rec.waste_pct or 0.0) / 100.0)

    @api.depends("net_qty", "rate")
    def _compute_amount(self):
        for rec in self:
            rec.amount = 0.0 if rec.display_type else rec.net_qty * rec.rate

    def _compute_currency_id(self):
        currency = self.env.company.currency_id
        for rec in self:
            rec.currency_id = currency

    @api.onchange("work_type_id")
    def _onchange_work_type_id(self):
        if self.work_type_id and self.work_type_id.default_cost_code_id and not self.cost_code_id:
            self.cost_code_id = self.work_type_id.default_cost_code_id

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            if not self.name or self.name == "New":
                self.name = self.product_id.display_name
            if self.product_id.uom_id:
                self.uom_id = self.product_id.uom_id
