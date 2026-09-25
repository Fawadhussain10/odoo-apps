from odoo.exceptions import UserError

from .common import ConstructionTestCommon


class TestBoq(ConstructionTestCommon):

    def test_manual_and_dimensional_formulas(self):
        project = self._create_project()
        wbs = project.wbs_ids[0]
        boq = self.env["construction.boq"].create({"name": "BOQ", "project_id": project.id})
        line = self.env["construction.boq.line"].create({
            "boq_id": boq.id, "wbs_id": wbs.id, "name": "Excavation",
            "formula_type": "manual", "number": 780, "waste_pct": 0, "rate": 25,
        })
        self.assertEqual(line.net_qty, 780)
        self.assertEqual(line.amount, 19500)

        dim_line = self.env["construction.boq.line"].create({
            "boq_id": boq.id, "wbs_id": wbs.id, "name": "Slab",
            "formula_type": "dimensional", "number": 1, "length": 20, "width": 15,
            "deduction": 10, "rate": 100,
        })
        self.assertEqual(dim_line.gross_qty, 300)
        self.assertEqual(dim_line.net_qty, 290)
        self.assertEqual(dim_line.amount, 29000)
        self.assertEqual(boq.total_amount, 19500 + 29000)

    def test_baseline_immutability_and_live_tracking_exception(self):
        project = self._create_project()
        boq, line, wbs = self._create_approved_boq(project)
        self.assertEqual(boq.state, "approved")
        self.assertTrue(boq.is_baseline)

        with self.assertRaises(UserError):
            line.write({"rate": 999})

        # live-tracking control quantities remain writable post-approval
        line.write({"forecast_qty": 950})
        self.assertEqual(line.forecast_qty, 950)

    def test_create_revision_supersedes_previous_baseline(self):
        project = self._create_project()
        boq, line, wbs = self._create_approved_boq(project)
        action = boq.action_create_revision()
        new_boq = self.env["construction.boq"].browse(action["res_id"])
        self.assertEqual(new_boq.revision_no, 2)
        self.assertEqual(new_boq.state, "draft")
        new_boq.line_ids[0].write({"rate": 1600})
        new_boq.action_submit()
        new_boq.action_negotiate()
        new_boq.action_confirm_contract()
        new_boq.action_approve()
        self.assertEqual(boq.state, "superseded")
        self.assertFalse(boq.is_baseline)
        self.assertTrue(new_boq.is_baseline)

    def test_variation_drives_revised_amount_only_when_approved(self):
        project = self._create_project()
        boq, line, wbs = self._create_approved_boq(project, qty=780, rate=25)
        variation = self.env["construction.variation"].create({
            "name": "Extra depth", "project_id": project.id, "boq_id": boq.id,
            "responsibility": "site_condition",
        })
        vline = self.env["construction.variation.line"].create({
            "variation_id": variation.id, "boq_line_id": line.id, "revised_qty": 800,
        })
        self.assertEqual(vline.delta_qty, 20)
        self.assertEqual(line.revised_net_qty, 780)  # not yet approved

        variation.action_submit_technical_review()
        variation.action_submit_commercial_eval()
        variation.action_submit_internal_approval()
        variation.action_submit_customer_approval()
        variation.action_approve()

        self.assertEqual(line.revised_net_qty, 800)
        self.assertEqual(line.revised_amount, 20000)

    def test_load_from_template_maps_wbs_by_stage(self):
        project = self._create_project()
        wbs = project.wbs_ids[0]
        template = self.env["construction.boq.template"].create({
            "name": "TEST Template", "category_id": self.category.id,
        })
        self.env["construction.boq.template.line"].create({
            "template_id": template.id, "stage_template_id": wbs.stage_template_id.id,
            "name": "Template Line A", "formula_type": "manual", "number": 100, "rate": 10,
        })
        boq = self.env["construction.boq"].create({"name": "BOQ", "project_id": project.id})
        boq.action_load_from_template(template)
        self.assertEqual(len(boq.line_ids), 1)
        self.assertEqual(boq.line_ids.wbs_id.stage_template_id, wbs.stage_template_id)
