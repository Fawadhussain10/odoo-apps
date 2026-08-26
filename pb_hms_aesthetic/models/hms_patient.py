#-*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

class PBPatient(models.Model):
    _name = "hms.patient"
    _inherit = ['portal.mixin', 'hms.patient']

    def _rec_count(self):
        rec = super(PBPatient, self)._rec_count()
        for rec in self:
            rec.aesthetic_wish_count = len(rec.sudo().aesthetic_wish_ids)

    aesthetic_wish_ids = fields.One2many('pb.aesthetic.patient.wish', 'patient_id', 'Aesthetic Wishes')
    aesthetic_wish_count = fields.Integer(compute='_rec_count', string='# Aesthetic Wishes')

    #Aesthetic CLINIC HISTORY (ach) FORM
    ach_any_treatement = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no", string="1. In the last year have you undergone medical treatment?")
    ach_dermatological_treatement = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no", string="2. In the last year have you undergone dermatological treatment?")
    ach_any_surgery = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no", string="3. In the last 9 months, have you had any surgery?")
    ach_surgery_comment = fields.Char(string="Surgery Details")

    ach_heart_problems = fields.Boolean(string="Heart problems")
    ach_cancer = fields.Boolean(string="Cancer")
    ach_diabetes = fields.Boolean(string="Diabetes")
    ach_epilepsy = fields.Boolean(string="Epilepsy")
    ach_hormonal_imbalance = fields.Boolean(string="Hormonal Imbalance")
    ach_column_damage = fields.Boolean(string="Column Damage")
    ach_veins = fields.Boolean(string="Veins")
    ach_varicose_veins = fields.Boolean(string="Varicose Veins")
    ach_hysterectomy = fields.Boolean(string="Hysterectomy")
    ach_thyroid_disease = fields.Boolean(string="Thyroid Disease")
    ach_systemic_disease = fields.Boolean(string="Systemic Disease (Hypertension, Circulatory, etc.)")
    ach_asthma = fields.Boolean(string="Asthma")
    ach_pregnancy = fields.Boolean(string="Pregnancy")
    ach_anticoagulants = fields.Boolean(string="Anticoagulants")
    ach_constipation = fields.Boolean(string="Constipation, Colon problems")
    ach_metal_implants = fields.Boolean(string="Metal Implants")
    ach_hiv = fields.Boolean(string="HIV (ACH)")
    ach_gastritis = fields.Boolean(string="Gastritis")
    ach_spasms = fields.Boolean(string="Spasms")
    ach_hemophilia = fields.Boolean(string="Hemophilia")
    ach_hypertension = fields.Boolean(string="Hypertension")
    ach_fibroids = fields.Boolean(string="Fibroids / Cysts")

    ach_medicines = fields.Text(string="5. List medications, supplements, vitamins, diuretics, weight loss tablets, etc. who are consuming regularly.")
    ach_smoke = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="6. Do you Smoke?")
    ach_exercise = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="7. Do you exercise regularly?")
    ach_diet = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="8. Do you follow a diet?")
    ach_regular_sleep = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="9. Do you have regular sleep patterns?")
    ach_contact_lenses = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="10. Do you wear contact lenses?")
    ach_pacemakers = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="11. Do you have metal implants or pacemakers?")

    #YOUR SKIN
    ach_water_temp = fields.Selection([('cold','Cold'), ('tibia','Tibia'), ('hot','Hot')
    ], default="cold", string="12. At what temperature do you use the water for cleaning at home?")
    ach_skin_problem = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no", string="13. Do you have a special problem on the skin of your face or body?")
    ach_skin_problem_comment = fields.Char(string="Other Skin Problem")

    #14. What products do you regularly use for skin care?
    ach_use_soap = fields.Boolean(string="Soap")
    ach_use_cleaner = fields.Boolean(string="Cleaner")
    ach_use_tonic = fields.Boolean(string="Tonic")
    ach_use_mask = fields.Boolean(string="Mask")
    ach_use_peeling = fields.Boolean(string="Peeling")
    ach_use_eye_pct = fields.Boolean(string="Eye Pct")
    ach_use_comment = fields.Char(string="Other Product Details")

    #EXFOLIATION STORY
    ach_undergone_chemical = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="15. Have you undergone chemical, laser or dermabrasion peels?")
    ach_undergone_chemical_in_month = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="In the last month?")

    ach_undergone_retina = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="16. Are you using Retin A, Renova or Adapalene?")
    ach_undergone_retina_in_3month = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="In the last 3 month?")

    ach_use_acne = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="17. Do you use acne or other pathology medications?")
    ach_use_acne_comment = fields.Char(string="Which one?")
    ach_use_acne_in_6_month = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="In the last 6 months?")
    ach_use_acne_in_6_month_comment = fields.Char(string="Please Specify")

    #18. Do you frequently use products that contain the following ingredients?
    ach_used_glycolic_acid = fields.Boolean(string="Glycolic Acid")
    ach_used_lactic_acid = fields.Boolean(string="Lactic acid")
    ach_used_grainy_scrub = fields.Boolean(string="Grainy Scrub")
    ach_used_hydroxyacid_prod = fields.Boolean(string="Hydroxyacid Prod")
    ach_used_derivatives_of_A = fields.Boolean(string="Derivatives of Vit A")

    #HYDRATION LEVEL
    ach_water_consume = fields.Selection([('4glass','1-4 Glasses'), ('8glasses','4-8 Glasses'), ('8plusglasses','> 8 Glasses')
    ], default="4glass", string="19. How much water do you consume daily?")
    ach_alcohole_consume = fields.Selection([('na', 'NA'), ('4cups','1-4 Cups'), ('8glasses','5-8 Glasses'), ('10plusglasses','> 10 Glasses')
    ], default="na", string="20. How many alcoholic beverages do you consume weekly?")

    #21. Have you experienced any of the following skin conditions?
    ach_skin_flaking = fields.Boolean(string="Flaking")
    ach_skin_tightness = fields.Boolean(string="Tightness")
    ach_skin_evident_dryness = fields.Boolean(string="Evident Dryness")

    ach_use_solar_screen_face = fields.Char(string="22. What Solar Screen FPS do you use for your Face?")
    ach_use_solar_screen_body = fields.Char(string="What Solar Screen FPS do you use for your Body?")

    ach_skin_tanning = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="23. Are you tanning?")

    #CAPILLARY ACTIVITY
    ach_suffer_from_burn = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="24. Does moderate sun exposure burn easily?")
    ach_suffer_from_blush = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="25. Do you blush easily when you are nervous?")
    ach_suffer_from_redness = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="26. Do you tend to redness?")
    ach_suffer_from_respiratory = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="27. Do you suffer from respiratory problems?")

    #NERVOUS ACTIVITY
    ach_use_cb = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="28. Do you consume caffeinated beverages (coffee, tea, soft drinks)?")
    ach_use_cb_per_day = fields.Char(string="How many per day?")

    ach_skin_itching = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="29. Do you experience burning or itching sensation on your skin?")
    ach_sensitivity_level = fields.Selection([('low','Low'), ('medium','Medium'), ('tall','Tall')
    ], string="30. What is your level of sensitivity to pain?")

    ach_claustrophobia = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="31. Have you experienced claustrophobia?")
    ach_massage_pressure = fields.Selection([('low','Low'), ('medium','Medium'), ('tall','Tall')
    ], string="32. What type of pressure do you prefer for your massage?")
    
    #33. Have you had a reaction to any of the following items?
    ach_reaction_cosmetics = fields.Boolean(string="Cosmetics")
    ach_reaction_medicine = fields.Boolean(string="Medicine")
    ach_reaction_iodine = fields.Boolean(string="Iodine")
    ach_reaction_pollen = fields.Boolean(string="Pollen")
    ach_reaction_food = fields.Boolean(string="Food")
    ach_reaction_hydroxy_acids = fields.Boolean(string="Hydroxy acids")
    ach_reaction_animals = fields.Boolean(string="Animals")
    ach_reaction_fragrances = fields.Boolean(string="Fragrances")
    ach_reaction_comment = fields.Char(string="Other Reactions")

    #ONLY FEMALE CUSTOMERS
    ach_use_contraceptives = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="34. Are you using oral contraceptives?")
    ach_pregnant = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="35. Are you pregnant or trying to get pregnant?")
    ach_breastfeeding = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="36. Are you breastfeeding?")
    ach_pregnancy_loss = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="37. Have you had a recent pregnancy loss?")
    
    #ONLY MALE CUSTOMERS
    #38. What method do you use to shave?
    ach_shave_electric = fields.Boolean(string="Electric")
    ach_shave_shaving = fields.Boolean(string="Shaving")
    ach_shave_damp = fields.Boolean(string="Damp")

    ach_shave_irritation = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="39. Do you experience irritation when shaving?")
    ach_embedded_hairs = fields.Selection([('no','NO'), ('yes','YES')
    ], default="no",string="40. Do you suffer from embedded hairs?")

    ach_signed_on = fields.Datetime("Signed On")
    ach_signature = fields.Binary("Signature")
    ach_has_to_be_signed = fields.Boolean("Tobe Signed", default=True)

    #Body Analysis
    #TECHNICAL DATA
    body_size = fields.Float(string="Size")
    current_weight = fields.Float(string="Current Weight")
    ideal_weight = fields.Float(string="Ideal Weight")

    obesity_type = fields.Selection([
        ('android','Android'), 
        ('gynecoid','Gynecoid'), 
    ], string="Type of Obesity")

    adipose_tissue_consistency = fields.Selection([
        ('hard','Hard'), 
        ('moderate','Moderate'),
        ('flaccid','Flaccid'), 
    ], string="Adipose Tissue Consistency")

    #STETOPATHOLOGIES
    state_of_cellulite = fields.Selection([
        ('dura','Dura'), 
        ('flaccid','Flaccid'),
        ('mixed','Mixed'),
        ('edemotosa','Edemotosa'),
    ], string="State Of Cellulite")

    muscle_flacity = fields.Selection([
        ('dermal','Dermal'), 
        ('mild','Mild'),
        ('moderate','Moderate'),
        ('severe','Severe'),
    ], string="Muscle Flacity")

    stretch_marks = fields.Selection([
        ('location','Location'), 
        ('color','Color'),
        ('evolution','Time of evolution'),
    ], string="Stretch Marks")
    trigger_factor = fields.Char(string="Trigger Factor")
    
    #Facial Analysis (Skin)
    skin_biotype = fields.Selection([
        ('alipic','Alipic'), 
        ('eudermica','Eudérmica'),
        ('grease','Grease'),
        ('mixed','Mixed'),
    ], string="Skin Biotype")
    coloration = fields.Selection([
        ('Yellowish','Yellowish'), 
        ('Reddish','Reddish'),
        ('Greyish','Greyish'),
        ('Normal','Normal'),
    ], string="Coloration")
    hydration_degree = fields.Selection([
        ('Dehydrated','Dehydrated'), 
        ('Very Dehydrated','Very dehydrated'),
        ('Hyper Hydrated','Hyper hydrated'),
    ], string="Hydration Degree")

    thickness = fields.Selection([
        ('Normal','Normal'), 
        ('Gross','Gross'),
        ('Fine','Fine'),
        ('Rough','Rough'),
    ], string="Thickness or Texture")

    #Acne
    acne_papules = fields.Boolean(string="Papules")
    acne_pustules = fields.Boolean(string="Pustules")
    acne_black_comedones = fields.Boolean(string="Black Comedones")
    acne_white_comedones = fields.Boolean(string="White Comedones")

    #Preauricular Wrinkles
    preauricular_wrinkles_front = fields.Boolean(string="Front")
    preauricular_wrinkles_backnose = fields.Boolean(string="Back-Nose")
    preauricular_wrinkles_frown = fields.Boolean(string="Frown")

    #Periocular wrinkles
    preauricular_wrinkles_nasogenian_sulcus = fields.Boolean(string="Nasogenian sulcus")
    preauricular_wrinkles_neck = fields.Boolean(string="Neck")
    preauricular_wrinkles_other = fields.Boolean(string="Others")

    #Skin Disorders
    skin_disorders_chloasmas = fields.Boolean(string="Chloasmas")
    skin_disorders_melasmas = fields.Boolean(string="Melasmas")
    skin_disorders_lentigines = fields.Boolean(string="Lentigines")
    skin_disorders_ephelides = fields.Boolean(string="Ephelides")
    skin_disorders_moles = fields.Boolean(string="Moles")
    skin_disorders_achromias = fields.Boolean(string="Achromias")
    skin_disorders_vitiligo = fields.Boolean(string="Vitiligo")
    skin_disorders_hair_alteration = fields.Boolean(string="Hair alteration")
    skin_disorders_large_pores = fields.Boolean(string="Large pores")
    skin_disorders_fragile_capillary = fields.Boolean(string="Fragile capillary")
    skin_disorders_flaccidity = fields.Boolean(string="Flaccidity")
    skin_disorders_premature_aging = fields.Boolean(string="Premature aging")

    #HOME CARE
    #Clean Routine
    routine_clear = fields.Boolean(string="Clear")
    routine_clear_comment = fields.Char(string="Clear Remark")
    routine_tone = fields.Boolean(string="Tone")
    routine_tone_comment = fields.Char(string="Tone Remark")
    routine_hydrated = fields.Boolean(string="Hydrated")
    routine_hydrated_comment = fields.Char(string="Hydrated Remark")
    routine_protection = fields.Boolean(string="Protection")
    routine_protection_comment = fields.Char(string="Protection Remark")

    #Phototype Skin Test
    skin_color = fields.Selection([
        ('0','Reddish'), 
        ('2','White-Beige'),
        ('4','Beige'),
        ('8','Light Brown'),
        ('12','Brown'),
        ('16','Black'),
    ], string="1. What is the natural color of your skin when it is not tanned?")

    hair_color = fields.Selection([
        ('0','Redhead, Light Blonde'), 
        ('2','Blonde, Light Brown'),
        ('4','Chestnut'),
        ('8','Dark Chestnut'),
        ('12','Dark Chestnut-Black'),
        ('16','Black'),
    ], string="2. What natural color is your hair?")

    eye_color = fields.Selection([
        ('0','Light Blue, Light Green, Gray'), 
        ('2','Blue, Green, Gray'),
        ('4','Gray, Light Brown'),
        ('8','Brown'),
        ('12','Dark Brown'),
        ('16','Black'),
    ], string="3. What color is the eyes?")
    freckles_number = fields.Selection([
        ('0','Many'), 
        ('4','Some'),
        ('6','A few'),
        ('8','None'),
    ], string="4. How many freckles does your body naturally have when you're not tanning?")
    genetic_heritage = fields.Selection([
        ('0','White breed with very white skin'), 
        ('2','White Skinned Race'),
        ('4','White race brown skin (Mediterranean)'),
        ('8','Middle East, Hindu, Asian, Hispanic-American'),
        ('12','Aboriginal, African, African American'),
    ], string="5. Which category best describes your genetic heritage?")
    burn_potential = fields.Selection([
        ('0','Always burns and never tans'), 
        ('2','Usually burns, but may lightly tan'),
        ('4','Burns occasionally, but tans moderately'),
        ('8','Never burns and tans easily'),
        ('10','Rarely burns and deeply tans'),
        ('12','Never burns'),
    ], string="6. Which category best describes your burn potential after one hour in the sun in the summer?")
    tanning_potential = fields.Selection([
        ('0','Never tans'), 
        ('2','Can be lightly tanned'),
        ('4','Can be tanned moderately'),
        ('8','Can be deeply tanned'),
    ], string="7. Which category best describes your tanning potential?")

    skin_score = fields.Integer(compute="_get_skin_score", string="Skin Score", store=True)
    skin_phototype = fields.Selection([
        ('phototype1','Very sensitive to sunlight'),
        ('phototype2','Sensitive to sunlight'),
        ('phototype3','Sensitive Normal to sunlight'),
        ('phototype4','The skin has tolerance to sunlight'),
        ('phototype5','The skin is dark and its tolerance is high'),
        ('phototype6','The skin is black and its tolerance is very high'),
    ], string="Skin Phototype", compute="_get_skin_score", store=True)
    filled_by_patient = fields.Boolean(string="Filled By Patient", default=False)

    face_mapping_ids = fields.One2many('pb.aesthetic.face.mapping', 'patient_id', string="Face Mapping")
    body_evolution_ids = fields.One2many('pb.aesthetic.body.evolution', 'patient_id', string="Body Evolution")

    @api.depends('skin_color','hair_color','eye_color','freckles_number','genetic_heritage','burn_potential','tanning_potential')
    def _get_skin_score(self):
        for rec in self:
            skin_score = int(rec.skin_color) + int(rec.hair_color) + int(rec.eye_color) + int(rec.freckles_number) + int(rec.genetic_heritage) + int(rec.burn_potential) + int(rec.tanning_potential)

            rec.skin_score = skin_score
            if skin_score <= 7:
                rec.skin_phototype = 'phototype1'
            if skin_score >= 8 and skin_score <= 21:
                rec.skin_phototype = 'phototype2'
            if skin_score >= 22 and skin_score <= 42:
                rec.skin_phototype = 'phototype3'
            if skin_score >= 43 and skin_score <= 68:
                rec.skin_phototype = 'phototype4'
            if skin_score >= 69 and skin_score <= 84:
                rec.skin_phototype = 'phototype5'
            if skin_score >= 85:
                rec.skin_phototype = 'phototype6'

    def action_view_aesthetic_wish(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_aesthetic.action_pb_aesthetic_patient_wish")
        action['domain'] = [('id', 'in', self.aesthetic_wish_ids.ids)]
        action['context'] = {'default_patient_id': self.id}
        return action

    def get_portal_sign_url(self):
        return "/my/aesthetic/%s/accept" % (self.id)

    def _get_report_base_filename(self):
        self.ensure_one()
        return '%s' % (self.name)

    def preview_aesthetic_hisotry(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': self.get_portal_url(),
        }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: