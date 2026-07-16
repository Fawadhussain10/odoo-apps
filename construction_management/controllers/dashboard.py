from odoo import http
from odoo.http import request

_ACTIVE_STATES = (
    "draft", "tender", "mobilization", "in_progress", "on_hold",
    "practical_completion", "defect_liability",
)

_MR_STATE_LABELS = {
    "draft": "Draft", "submitted": "Submitted", "site_approved": "Site Approved",
    "store_checked": "Store Checked", "procurement_approved": "Procurement Approved",
    "rfq_created": "RFQ Created", "partially_fulfilled": "Partially Fulfilled",
    "fulfilled": "Fulfilled", "closed": "Closed", "cancelled": "Cancelled",
}

_PROJECT_STATE_LABELS = {
    "draft": "Draft", "tender": "Tender/Awarded", "mobilization": "Mobilization",
    "in_progress": "In Progress", "on_hold": "On Hold",
    "practical_completion": "Practical Completion", "defect_liability": "Defect Liability",
    "closed": "Closed", "cancelled": "Cancelled",
}


class ConstructionDashboardController(http.Controller):

    @http.route("/construction_management/dashboard_data", type="jsonrpc", auth="user", readonly=True)
    def dashboard_data(self):
        env = request.env
        currency = env.company.currency_id
        Project = env["project.project"]
        projects = Project.search([("is_construction", "=", True)])
        active_projects = projects.filtered(lambda p: p.construction_state in _ACTIVE_STATES)

        revised_budget = sum(projects.mapped("revised_budget"))
        variance_at_completion = sum(projects.mapped("variance_at_completion"))
        kpis = {
            "active_projects": len(active_projects),
            "total_projects": len(projects),
            "original_budget": sum(projects.mapped("original_budget")),
            "revised_budget": revised_budget,
            "committed_amount": sum(projects.mapped("committed_amount")),
            "actual_cost": sum(projects.mapped("actual_cost")),
            "eac": sum(projects.mapped("eac")),
            "variance_at_completion": variance_at_completion,
            "variance_pct": (variance_at_completion / revised_budget) if revised_budget else 0.0,
            "open_material_requests": env["construction.material.request"].search_count(
                [("project_id", "in", projects.ids), ("state", "not in", ("fulfilled", "closed", "cancelled"))]
            ),
            "pending_ra_certificates": env["construction.ra.certificate"].search_count(
                [("subcontract_id.project_id", "in", projects.ids), ("state", "=", "draft")]
            ),
            "open_ncrs": env["construction.ncr"].search_count(
                [("project_id", "in", projects.ids), ("state", "!=", "closed")]
            ),
        }

        project_rows = []
        for p in active_projects.sorted(key=lambda p: p.revised_budget, reverse=True)[:12]:
            project_rows.append({
                "id": p.id,
                "name": p.name,
                "state": p.construction_state,
                "state_label": _PROJECT_STATE_LABELS.get(p.construction_state, p.construction_state),
                "original_budget": p.original_budget,
                "revised_budget": p.revised_budget,
                "actual_cost": p.actual_cost,
                "committed_amount": p.committed_amount,
                "eac": p.eac,
                "variance_pct": p.variance_pct,
                "physical_progress": sum(p.wbs_ids.mapped("progress_physical")) / len(p.wbs_ids) if p.wbs_ids else 0.0,
                "schedule_progress": sum(p.wbs_ids.mapped("progress_schedule")) / len(p.wbs_ids) if p.wbs_ids else 0.0,
                "rag_status": p.evm_rag_status or "green",
                "cpi": p.evm_cpi,
                "spi": p.evm_spi,
            })

        status_counts = {}
        for p in projects:
            status_counts[p.construction_state] = status_counts.get(p.construction_state, 0) + 1
        project_status_breakdown = [
            {"label": _PROJECT_STATE_LABELS.get(state, state), "value": count}
            for state, count in status_counts.items()
        ]

        mr_groups = env["construction.material.request"]._read_group(
            [("project_id", "in", projects.ids)], ["state"], ["__count"]
        )
        material_request_status = [
            {"label": _MR_STATE_LABELS.get(state, state or "Draft"), "value": count}
            for state, count in mr_groups
        ]

        Wbs = env["construction.wbs"]
        overrun_wbs = Wbs.search(
            [("project_id", "in", active_projects.ids), ("revised_budget", ">", 0)],
            order="variance_at_completion asc", limit=6,
        )
        top_overruns = [{
            "name": w.complete_name,
            "project": w.project_id.name,
            "revised_budget": w.revised_budget,
            "eac": w.eac,
            "variance_at_completion": w.variance_at_completion,
            "variance_pct": (w.variance_at_completion / w.revised_budget) if w.revised_budget else 0.0,
        } for w in overrun_wbs]

        rag_counts = {"green": 0, "amber": 0, "red": 0}
        for w in Wbs.search([("project_id", "in", active_projects.ids)]):
            if w.rag_status:
                rag_counts[w.rag_status] = rag_counts.get(w.rag_status, 0) + 1

        Subcontract = env["construction.subcontract"]
        subcontracts = Subcontract.search([("project_id", "in", projects.ids)])
        commercial = {
            "contract_value": sum(subcontracts.mapped("contract_value")),
            "certified_value": sum(subcontracts.mapped("certified_value")),
            "retention_held": sum(subcontracts.mapped("retention_held")),
            "advance_recovered": sum(subcontracts.mapped("advance_recovered")),
        }

        PO = env["purchase.order.line"]
        open_commitment_lines = PO.search([
            ("construction_project_id", "in", projects.ids), ("state", "=", "purchase"),
        ])
        procurement = {
            "open_po_value": sum(open_commitment_lines.mapped("price_subtotal")),
            "open_po_count": len(open_commitment_lines.mapped("order_id")),
            "pending_site_receipts": env["construction.site.receipt"].search_count(
                [("project_id", "in", projects.ids), ("state", "=", "draft")]
            ),
        }

        return {
            "currency_symbol": currency.symbol,
            "currency_position": currency.position,
            "kpis": kpis,
            "projects": project_rows,
            "project_status_breakdown": project_status_breakdown,
            "material_request_status": material_request_status,
            "top_overruns": top_overruns,
            "rag_counts": rag_counts,
            "commercial": commercial,
            "procurement": procurement,
        }
