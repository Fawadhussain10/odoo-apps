from odoo import _, api, models
from odoo.tools import format_datetime


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    @api.model_create_multi
    def create(self, vals_list):
        events = super().create(vals_list)
        events._li_track_meetings()
        return events

    def write(self, vals):
        res = super().write(vals)
        if 'opportunity_id' in vals:
            self._li_track_meetings()
        return res

    def _li_track_meetings(self):
        """A meeting on a lead coming from a LinkedIn prospect: stage Meeting and
        one meeting_booked event per lead (6.5)."""
        Event = self.env['li.event'].sudo()
        for meeting in self.sudo().filtered(lambda m: m.opportunity_id.li_prospect_id):
            lead = meeting.opportunity_id
            if Event.search_count([('crm_lead_id', '=', lead.id), ('event_type', '=', 'meeting_booked')]):
                continue
            prospect = lead.li_prospect_id
            if prospect.stage not in ('do_not_contact',):
                prospect.stage = 'meeting'
            when = format_datetime(self.env, meeting.start, tz=meeting.user_id.tz or self.env.user.tz,
                                   dt_format='d MMM y, HH:mm') if meeting.start else ''
            line = _('Meeting booked on %s', when)
            Event._log('meeting_booked', 'system', persona=prospect.persona_id, prospect=prospect, lead=lead,
                       detail=line, prospect_body=line, lead_body=line)
