# -*- coding: utf-8 -*-

from odoo import fields, models


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    # Registers our own "pb_map" view type (Patient Map) so hms.patient can
    # ship a <pb_map> arch and list it in an action's view_mode.
    # Deliberately NOT named 'map': this Odoo install already has
    # Enterprise's web_map installed, which claims that name with its own
    # RelaxNG schema (no bare <field> children allowed) - reusing "map" here
    # collides with it. We don't depend on web_map; this is fully custom.
    # Also deliberately NOT "pb_patient_map": Odoo's view-switcher renders
    # one button per view type with class "o_<type>", e.g. "o_pb_patient_map"
    # - which collided with the standalone map page's own root div class of
    # the same name and leaked its control-panel styling onto every other
    # Patients tab (that button sits in the shared control panel, always in
    # the DOM regardless of which tab is active). "pb_map" can't collide
    # with .o_pb_patient_map / .o_pb_patient_map_view.
    type = fields.Selection(
        selection_add=[('pb_map', 'Patient Map')],
        ondelete={'pb_map': 'cascade'},
    )

    def _get_view_info(self):
        # Client-side view-type validation (viewRegistry.addValidation in
        # views/view.js) requires "type in session.view_info", which is built
        # from this dict - just adding the type to the Selection above isn't
        # enough, or the "Map" tab throws "'type' is not valid" on load.
        return {'pb_map': {'icon': 'fa fa-map-marker'}} | super()._get_view_info()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
