from odoo.tests import TransactionCase


class ConstructionTestCommon(TransactionCase):
    """Shared fixtures for construction_management tests. Each test method runs inside its own
    savepoint (TransactionCase default), so nothing here needs manual cleanup."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env.ref("construction_management.project_category_construction")
        cls.subcategory = cls.env.ref("construction_management.project_subcategory_house")
        cls.product = cls.env["product.product"].create({
            "name": "TEST Cement Bag",
            "purchase_ok": True,
            "type": "consu",
            "is_storable": True,
        })
        cls.service_product = cls.env["product.product"].create({
            "name": "TEST Subcontract Labour",
            "purchase_ok": True,
            "type": "service",
        })
        cls.partner = cls.env["res.partner"].create({"name": "TEST Vendor/Customer"})

    def _create_project(self, name="TEST Project"):
        project = self.env["project.project"].create({
            "name": name,
            "is_construction": True,
            "construction_category_id": self.category.id,
            "construction_subcategory_id": self.subcategory.id,
        })
        project.action_generate_wbs_from_category()
        return project

    def _create_approved_boq(self, project, qty=1000, rate=1450):
        wbs = project.wbs_ids[0]
        boq = self.env["construction.boq"].create({"name": "Main BOQ", "project_id": project.id})
        line = self.env["construction.boq.line"].create({
            "boq_id": boq.id,
            "wbs_id": wbs.id,
            "name": "Cement",
            "product_id": self.product.id,
            "uom_id": self.product.uom_id.id,
            "formula_type": "manual",
            "number": qty,
            "rate": rate,
        })
        boq.action_submit()
        boq.action_negotiate()
        boq.action_confirm_contract()
        boq.action_approve()
        return boq, line, wbs
