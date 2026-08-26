# -*- coding: utf-8 -*-
#Ref was taken form GNU HEALTH ophthalmology module

from odoo import api, fields, models ,_
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta


class PBOphthalmologyEvaluation(models.Model):
    _name = "pb.ophthalmology.evaluation"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Ophthalmology Evaluation"

    @api.depends('patient_id', 'patient_id.birthday', 'date')
    def get_patient_age(self):
        for rec in self:
            age = ''
            if rec.patient_id.birthday:
                end_data = rec.date or fields.Datetime.now()
                delta = relativedelta(end_data, rec.patient_id.birthday)
                if delta.years <= 2:
                    age = str(delta.years) + _(" Year") + str(delta.months) + _(" Month ") + str(delta.days) + _(" Days")
                else:
                    age = str(delta.years) + _(" Year")
            rec.age = age

    STATES = {'cancel': [('readonly', True)], 'done': [('readonly', True)]}

    name = fields.Char(string='Name', default='/', copy=False, tracking=True)
    patient_id = fields.Many2one('hms.patient', 'Patient', required=True, tracking=True)
    date = fields.Datetime('Date', default=fields.Datetime.now, help="Date of Consultation", tracking=True)
    age = fields.Char(compute="get_patient_age", string='Age', store=True,
            help="Computed patient age at the moment of the evaluation")
    physician_id = fields.Many2one('hms.physician', ondelete='restrict', string='Physician', 
        index=True, help='Physician\'s Name')
    appointment_id = fields.Many2one('hms.appointment', ondelete="restrict", 
        string='Appointment')
    diseases_ids = fields.Many2many("hms.diseases", 'hms_diseases_ophthalmology_rel', 'evaluation_id', 'diseases_id', "Disease")

    # there are two types of charts, a meter chart.. 6/.. val
    # and ft chart.. 200/...
    snellen_chart = [
        ('6_6', '6/6'),
        ('6_9', '6/9'),
        ('6_12', '6/12'),
        ('6_18', '6/18'),
        ('6_24', '6/24'),
        ('6_36', '6/36'),
        ('6_60', '6/60'),
        ('5_60', '5/60'),
        ('4_60', '4/60'),
        ('3_60', '3/60'),
        ('2_60', '2/60'),
        ('1_60', '1/60'),
        ('1_meter_fc', '1 Meter FC'),
        ('1_2_meter_fc', '1/2 Meter FC'),
        ('hmfc', 'HMCF'),
        ('p_l', 'P/L')]

    # Near vision chart
    near_vision_chart = [
        ('N6', 'N6'),
        ('N8', 'N8'),
        ('N12', 'N12'),
        ('N18', 'N18'),
        ('N24', 'N24'),
        ('N36', 'N36'),
        ('N60', 'N60')]
    # vision test using snellen chart
    rdva = fields.Selection(snellen_chart, 'RDVA', help="Right Eye Vision of Patient without aid")
    ldva = fields.Selection(snellen_chart, 'LDVA', help="Left Eye Vision of Patient without aid")
    # vision test using pinhole accurate manual testing
    rdva_pinhole = fields.Selection(snellen_chart, 'RDVA Using Pin Hole',
        help="Right Eye Vision Using Pin Hole")
    ldva_pinhole = fields.Selection(snellen_chart, 'LDVA Using Pin Hole',
        help="Left Eye Vision Using Pin Hole")

    # vison testing with glasses just to assess what the patient sees with
    # his existing aid # useful esp with vision syndromes that are not
    # happening because of the lens
    rdva_aid = fields.Selection(snellen_chart, 'RDVA AID', help="Vision with glasses or contact lens")
    ldva_aid = fields.Selection(snellen_chart, 'LDVA AID', help="Vision with glasses or contact lens")

    # spherical
    rspherical = fields.Float('RSPH', help='Right Eye Spherical')
    lspherical = fields.Float('LSPH', help='Left Eye Spherical')

    rcylinder = fields.Float('R-CYL', help='Right Eye Cylinder')
    lcylinder = fields.Float('L-CYL', help='Left Eye Cylinder')

    raxis = fields.Float('R-Axis', help='Right Eye Axis')
    laxis = fields.Float('L-Axis', help='Left Eye Axis')

    # near vision testing .... you will get it when u cross 40 :)
    # its also thinning of the lens.. the focus falls behind the retina
    # in case of distant vision the focus does not reach retina
    rnv_add = fields.Float('R-NV Add', help='Right Eye Best Corrected NV Add')
    lnv_add = fields.Float('L-NV Add', help='Left Eye Best Corrected NV Add')
    
    rnv = fields.Selection(near_vision_chart, 'RNV', help="Right Eye Near Vision")
    lnv = fields.Selection(near_vision_chart, 'LNV', help="Left Eye Near Vision")

    # after the above tests the optometrist or doctor comes to a best conclusion
    # best corrected visual acuity
    # the above values are from auto refraction
    # the doctors decision is final
    # and there could be changes in values of cylinder, spherical and axis
    # these values will go into final prescription of glasses or contact lens
    # by default these values should be auto populated 
    # and should be modifiable by an ophthalmologist
    rbcva_spherical = fields.Float('R-Corrected SPH', help='Right Eye Best Corrected Spherical')
    lbcva_spherical = fields.Float('L-Corrected SPH', help='Left Eye Best Corrected Spherical')

    rbcva_cylinder = fields.Float('R-Corrected CYL', help='Right Eye Best Corrected Cylinder')
    lbcva_cylinder = fields.Float('L-Corrected CYL', help='Left Eye Best Corrected Cylinder')

    rbcva_axis = fields.Float('R-Corrected Axis', help='Right Eye Best Corrected Axis')
    lbcva_axis = fields.Float('L-Corrected Axis', help='Left Eye Best Corrected Axis')

    rbcva = fields.Selection(snellen_chart, 'RBCVA', help="Right Eye Best Corrected VA")
    lbcva = fields.Selection(snellen_chart, 'LBCVA', help="Left Eye Best Corrected VA")
    
    rbcva_nv_add = fields.Float('R-BCVA - Add', help='Right Eye Best Corrected NV Add')
    lbcva_nv_add = fields.Float('L-BCVA - Add', help='Left Eye Best Corrected NV Add')

    rbcva_nv = fields.Selection(near_vision_chart, 'RBCVANV', help="Right Eye Best Corrected Near Vision")
    lbcva_nv = fields.Selection(near_vision_chart, 'LBCVANV', help="Left Eye Best Corrected Near Vision")

    #some other tests of the eyes
    #useful for diagnosis of glaucoma a disease that builds up
    #pressure inside the eye and destroy the retina
    #its also called the silent vision stealer
    #intra ocular pressure
    #there are three ways to test iop
    #   SCHIOTZ
    #   NONCONTACT TONOMETRY
    #   GOLDMANN APPLANATION TONOMETRY

    notes = fields.Text ('Notes', states=STATES)

    #Intraocular Pressure 
    iop_method = fields.Selection([
        ('nct', 'Non-contact tonometry'),
        ('schiotz', 'Schiotz tonometry'),
        ('goldmann', 'Goldman tonometry'),
        ], 'Method', help='Tonometry / Intraocular pressure reading method')
    riop = fields.Float('RIOP', help="Right Intraocular Pressure in mmHg")
    liop = fields.Float('LIOP', help="Left Intraocular Pressure in mmHg")
    findings_ids = fields.One2many('pb.ophthalmology.finding', 'evaluation_id', string='Findings')

    state = fields.Selection([('draft', 'Draft'),
        ('in_progress', 'In progress'),
        ('done', 'Done'),
        ], 'Status', default="draft", readonly=True)

    def unlink(self):
        for data in self:
            if data.state in ['done']:
                raise UserError(_('You can not delete record in done state'))
        return super(PBOphthalmologyEvaluation, self).unlink()

    def action_done(self):
        self.state = 'done'

    def action_inprogress(self):
        if self.name=='/':
            self.name = self.env['ir.sequence'].next_by_code('pb.ophthalmology.evaluation')
        self.state = 'in_progress'


class PbOphthalmologyFindings(models.Model):
    _name = "pb.ophthalmology.finding"
    _description = "Ophthalmology Finding"
    
    evaluation_id = fields.Many2one('pb.ophthalmology.evaluation', 'Evaluation', required=True, ondelete="cascade")
    eye_structure = fields.Selection([('lid', 'Lid'),
        ('ncs', 'Naso-lacrimal system'),
        ('conjuctiva', 'Conjunctiva'),
        ('cornea', 'Cornea'),
        ('anterior_chamber', 'Anterior Chamber'),
        ('iris', 'Iris'),
        ('pupil', 'Pupil'),
        ('lens', 'Lens'),
        ('vitreous', 'Vitreous'),
        ('fundus_disc', 'Fundus Disc'),
        ('macula', 'Macula'),
        ('fundus_background', 'Fundus background'),
        ('fundus_vessels', 'Fundus vessels'),
        ('other', 'Other'),
        ], 'Structure',help="Affected eye structure")
    affected_eye = fields.Selection([
        ("right","right"),
        ("left","left"),
        ("both","both")], string='Eye', default="right", required=True, help="Affected eye")
    finding = fields.Char('Finding')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:   