# -*- encoding: utf-8 -*-
from odoo import api, fields, models,_

class Appointment(models.Model):
    _inherit = "hms.appointment"

    READONLY_STATES = {'cancel': [('readonly', True)], 'done': [('readonly', True)]}

    vital_symptom_ids = fields.Many2many(
        'hms.vital.symptom', 'hms_appointment_vital_symptom_rel', 'appointment_id', 'symptom_id',
        string='Review of Systems',
        help='Symptoms reported present during the review of systems, grouped by body area.')

    loc = fields.Integer("Level of Consciousness", help="Level of consciousness (LOC) is a medical term for identifying how awake, alert, and aware of their surroundings someone is.")
    loc_eyes = fields.Selection([
            ('1', 'Does not Open Eyes'),
            ('2', 'Opens eyes in response to painful stimuli'),
            ('3', 'Opens eyes in response to voice'),
            ('4', 'Opens eyes spontaneously'),
        ], string='Glasgow - Eyes')
    loc_verbal = fields.Selection([
            ('1', 'Make no sounds'),
            ('2', 'Incomprehensible Sounds'),
            ('3', 'Utters inappropriate words'),
            ('4', 'Confused,disoriented'),
            ('5', 'Oriented, converses normally'),
        ], string='Glasgow - Verbal')
    loc_motor = fields.Selection([
            ('1', 'Make no movement'),
            ('2', 'Extension to painful stimuli decerebrate response'),
            ('3', 'Abnormal flexion to painful stimuli decerebrate response'),
            ('4', 'Flexion/Withdrawal to painful stimuli '),
            ('5', 'Localizes painful stimuli'),
            ('6', 'Obeys commands'),
        ], string='Glasgow - Motor')

    mood = fields.Selection([
            ('n', 'Normal'),
            ('s', 'Sad'),
            ('f', 'Fear'),
            ('r', 'Rage'),
            ('h', 'Happy'),
            ('d', 'Disgust'),
            ('e', 'Euphoria'),
            ('fl', 'Flat'),
        ], string='Mood', help="a conscious state of mind or predominant emotion.")
    violent = fields.Boolean('Violent Behaviour')
    orientation = fields.Boolean('Orientation', help="Orientation is something healthcare providers check when screening for dementia and evaluating cognitive abilities.")
    memory = fields.Boolean('Memory', help="The ability to recover information about past events or knowledge.")
    knowledge_current_events = fields.Boolean('Knowledge of Current Events')
    judgment = fields.Boolean('Jugdment', help="the ability to make logical, rational decisions and decide whether a given action is right or wrong.")
    symptom_proctorrhagia = fields.Boolean('Polyphagia', help="excessive appetite or eating.")
    abstraction = fields.Boolean('Abstraction', help="the mental process of forming ideas that are theoretical or representational rather than concrete.")
    vocabulary = fields.Boolean('Vocabulary')
    #symptom_pain = fields.Boolean('Pain', help="The International Association for the Study of Pain defines pain as an unpleasant sensory and emotional experience associated with, or resembling that associated with, actual or potential tissue damage. In medical diagnosis, pain is regarded as a symptom of an underlying condition.")
    calculation_ability = fields.Boolean('Calculation Ability')
    object_recognition = fields.Boolean('Object Recognition', help="object recognition - the visual perception of familiar objects. beholding, seeing, visual perception - perception by means of the eyes.")
    praxis = fields.Boolean('Praxis', help="Praxis is the medical term for motor planning and dyspraxia is the inability to plan movement. ... Motor planning is a three step process where a child is required to: Conceive or imagine a task (Ideation)")

    #Physical Examination
    #Head
    pe_head_sign_symptoms_of_infection = fields.Selection([('na','N/A'),
        ('no','NO'), ('yes','YES')
    ], default="na", string="Signs and Symptoms of infection", help="A symptom is a manifestation of disease apparent to the patient himself, while a sign is a manifestation of disease that the physician perceives. The sign is objective evidence of disease; a symptom, subjective.")
    pe_head_symmetry = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('abnormal','Abnormal')
    ], default="na", string="Shape/Symmetry", help=" correspondence in size, shape, and relative position of parts on opposite sides of a dividing line or median plane or about a center or axis — see bilateral symmetry, radial symmetry.")

    #Eyes
    pe_eyes_equal = fields.Selection([('na','N/A'),
        ('no','NO'), ('yes','YES')
    ], default="na", string="Equal", help="he pupils are in the center of the iris, which is the colored part of your eye. They control how much light enters the eye by shrinking and widening. Equal.")
    pe_eyes_rlarge = fields.Boolean(string="R larger")
    pe_eyes_llarge = fields.Boolean(string="L larger")

    pe_eyes_reactive_to_light = fields.Selection([('na','N/A'),
        ('no','NO'), ('yes','YES')
    ], default="na", string="Reactive to light", help="This condition is called anisocoria and may be harmless. But it can also be a sign that you have a serious health issue in your brain, blood vessels, or nerves.")

    pe_eyes_round = fields.Selection([('na','N/A'),
        ('no','NO'), ('yes','YES')
    ], default="na", string="Round")
    pe_eyes_rabnormal = fields.Boolean(string="R abnormal shape")
    pe_eyes_labnormal = fields.Boolean(string="L abnormal shape")

    pe_eyes_reaction = fields.Selection([('na','N/A'),
        ('brisk','Brisk'), ('sluggish','Sluggish')
    ], default="na", string="Reaction")
    pe_eyes_rnoreaction = fields.Boolean(string="R No Reaction")
    pe_eyes_lnoreaction = fields.Boolean(string="L No Reaction")

    pe_eyes_accomodation = fields.Selection([('na','N/A'),
        ('right','Right'), ('left','Left')
    ], default="na", string="Accomodation", help=" In medicine, the ability of the eye to change its focus from distant to near objects.")

    #Ears
    pe_ears_symmetry = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('abnormal','Abnormal')
    ], default="na", string="Symmetry", help="Equality or correspondence in form of parts distributed around a center or an axis, at the extremities or poles, or on the opposite sides of any body.")
    pe_ears_lesion = fields.Selection([('na','N/A'),
        ('no','NO'), ('yes','YES')
    ], default="na", string="Ear Lesion", help="The lesions are erythematous, scaly patches or plaques with irregular borders which can occur anywhere on the skin.")
    pe_ears_lesion_comment = fields.Char(string="Ear Lesion Describe")
    pe_ears_gross_hearing = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('abnormal','Abnormal')
    ], default="na", string="Gross Hearing")

    #Nose
    pe_nose_congestion = fields.Selection([('na','N/A'),
        ('no','NO'), ('yes','YES')
    ], default="na", string="Congestion", help="An abnormal or excessive accumulation of a body fluid. The term is used broadly in medicine.")
    pe_nose_drainage = fields.Selection([('na','N/A'),
        ('no','NO'), ('yes','YES')
    ], default="na", string="Drainage", help=" In medicine, to remove fluid as it collects; or, a tube or wick-like device used to remove fluid from a body cavity, wound, or infected area.")
    pe_nose_drainage_comment = fields.Char(string="Drainage Describe")
    pe_nose_smell = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('abnormal','Abnormal')
    ], default="na", string="Smell", help="The sense of smell or the act of smelling.")

    #Mouth/Throat
    pe_mouth_visual = fields.Selection([('na','N/A'),
        ('moist','Moist'), ('pink','Pink'), ('intact','Intact')
    ], default="na", string="Visual", help="Medical Terminology Ophthalm/o = Eye Ophthalm/o = Eye Ophthalm/o = Eye Opt/o = Vision.")
    pe_mouth_lesion = fields.Selection([('na','N/A'),
        ('no','NO'), ('yes','YES')
    ], default="na", string="Mouth Lesion", help="Oral lesions are mouth ulcers or sores, which may be painful. They can include abnormal cell growth and rare tongue and hard-palate (roof of mouth) disorders.")
    pe_mouth_lesion_comment = fields.Char(string="Mouth Lesion Describe")
    pe_mouth_missing_teeth = fields.Selection([('na','N/A'),
        ('no','NO'), ('yes','YES')
    ], default="na", string="Missing Teeth/Dentures")
    pe_nose_odor = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('abnormal','Abnormal')
    ], default="na", string="Odor", help="a quality of something that stimulates the olfactory organ : smell.")
    pe_nose_swallow = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('abnormal','Abnormal')
    ], default="na", string="Swallow", help="swallowing, also called Deglutition, the act of passing food from the mouth, by way of the pharynx (or throat) and esophagus, to the stomach.")
    pe_nose_tracheal_alignment = fields.Selection([('na','N/A'),
        ('regular','Regular'), ('irregular','Irregular')
    ], default="na", string="Tracheal Alignment", help="The trachea is one of the most important parts of the respiratory system and damage to the trachea can indicate a life-threatening emergency.")
    pe_nose_lymp_nodes = fields.Selection([('na','N/A'),
        ('regular','Regular'), ('irregular','Irregular')
    ], default="na", string="Lymp Nodes", help=" A small bean-shaped structure that is part of the body's immune system.")

    #Skin
    pe_skin_color = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('dry','Dry')
    ], default="na", string="Color/Moisture")
    pe_skin_temperature = fields.Selection([('na','N/A'),
        ('warm','Warm to Touch'), ('cold','Cold to Touch')
    ], default="na", string="Temperature")
    pe_skin_lesions = fields.Selection([('na','N/A'),
                        ('no','NO'), ('yes','YES')
                    ], default="na", string="Skin Lesions", help="A skin lesion is a part of the skin that has an abnormal growth or appearance compared to the skin around it.")
    pe_skin_lesions_comment = fields.Char(string="Skin Lesion Describe")

    #Neck
    pe_neck_veins = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('dry','Dry')
    ], default="na", string="Veins", help="A blood vessel that carries blood that is low in oxygen content from the body back to the heart.")
    pe_neck_visual = fields.Selection([('na','N/A'),
        ('warm','Warm to touch'), ('cold','Cold to touch')
    ], default="na", string="Neck Visual")
    pe_neck_palpitation = fields.Selection([('na','N/A'),
        ('no','NO'), ('yes','YES')
    ], default="na", string="Neck Palpitation")

    #Chest
    pe_chest_movements = fields.Selection([('na','N/A'),
        ('symmetrical','Symmetrical'), ('asymmetrical','Asymmetrical'), ('shallow','Shallow')
    ], default="na", string="Chest Movements", help="Chest expansion on inspiration should be the same or similar on each breath.")
    pe_chest_auscultation = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('hyperinflation','Hyperinflation'),
        ('wheeze','Wheeze'), ('cripitation','Cripitation'),
    ], default="na", string="Chest Auscultation", help="the act of listening to sounds arising within organs (as the lungs or heart) as an aid to diagnosis and treatment.")
    pe_chest_breathing_sounds = fields.Selection([('na','N/A'),
        ('depth','Depth'), ('equal','Equal')
    ], default="na", string="Breathing Sounds")

    #CARDIOVASCULAR
    #Skin/Mucous membrane
    pe_cardio_membrane = fields.Selection([('na','N/A'),
        ('pink','Pink'), ('pale','Pale'), ('cyanotic','Cyanotic'), ('jaundice','Jaundice'),
        ('ruddy','Ruddy'), ('flashed','Flashed'), ('diaphoretic','Diaphoretic')
    ], default="na", string="Skin/Mucous membrane", help="The moist, inner lining of some organs and body cavities (such as the nose, mouth, lungs, and stomach).")

    #Pulse
    pe_pulse_radial = fields.Selection([('na','N/A'),
        ('rpalpable','R Palpable'), ('lpalpable','L Palpable'),
        ('rabsent','R Absent'), ('labsent','L Absent'),
    ], default="na", string="Radial", help="arranged or having parts arranged like rays.")
    pe_pulse_pedal = fields.Selection([('na','N/A'),
        ('rpalpable','R Palpable'), ('lpalpable','L Palpable'),
        ('rabsent','R Absent'), ('labsent','L Absent'),
    ], default="na", string="Pedal", help="pertaining to the foot or feet.")
    pe_pulse_apical_radial = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('pulse_deficit','Pulse Deficit'),
    ], default="na", string="Apical-Radial", help="The apical pulse is a pulse site on the left side of the chest over the pointed end, or apex, of the heart.")
    pe_pulse_carotid = fields.Selection([('na','N/A'),
        ('right','Right'), ('left','Left'),
        ('thrill','Thrill'), ('bruit','Bruit'),
    ], default="na", string="Carotid", help="Pertaining to the carotid artery and the area near that key artery, which is located in the front of the neck.")

    #Capillary Refill
    pe_capillary_refill = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('delayed','Delayed'),
    ], default="na", string="(<3 Sec)")

    #Jugular Vein
    pe_jugular_vein_visual = fields.Selection([('na','N/A'),
        ('not_visible','Not Visible'), ('visible','Visible'),
    ], default="na", string="Jugular Vein Visual")

    #Edema
    pe_edema_present = fields.Selection([('na','N/A'),
        ('pitting','Pitting'), ('non_pitting','Non-pitting'),
    ], default="na", string="Present", help="To appear or be felt first during birth. Used of the part of the fetus that proceeds first through the birth canal.")

    #Hearth Rhythm
    pe_hr_auscultation = fields.Selection([('na','N/A'),
        ('regular','Regular'), ('irregular','Irregular'),
        ('murmur','Murmur'), ('faint','Faint'), ('muffled','Muffled')
    ], default="na", string="Edema Auscultation", help="Auscultation is listening to the sounds of the body during a physical examination.")

    #Device
    pe_device_pacemaker = fields.Selection([('na','N/A'),
        ('no','NO'), ('yes','YES')
    ], default="na", string="Pacemaker", help="a group of cells or a body part that serves to establish and maintain a rhythmic activity.")
    pe_device_pacemaker_comment = fields.Char(string="Pacemaker Describe", help="A pacemaker is a small device that's placed (implanted) in your chest to help control your heartbeat.")

    #GIT
    #Abdomen
    pe_git_shape = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('distended','Distended'),
        ('scaphoid','Scaphoid'), ('tender','Tender')
    ], default="na", string="Shape")

    #4-Quadrant
    pe_git_luq = fields.Selection([('na','N/A'),
        ('active','Active'), ('hyper','Hyper'), ('absent','Absent')
    ], default="na", string="LUQ", help="Left upper quadrant (LUQ) pain means pain in the left upper abdominal region.")

    #(Auscultation)
    pe_git_ruq = fields.Selection([('na','N/A'),
        ('active','Active'), ('hyper','Hyper'), ('absent','Absent')
    ], default="na", string="RUQ", help="RUQ: Right upper quadrant, the upper-right quarter of the abdomen.")
    pe_git_llq = fields.Selection([('na','N/A'),
        ('active','Active'), ('hyper','Hyper'), ('absent','Absent')
    ], default="na", string="LLQ", help="LLQ: Left lower quadrant (quarter). For example, the LLQ of the abdomen contains the descending portion of the colon.")
    pe_git_rlq = fields.Selection([('na','N/A'),
        ('active','Active'), ('hyper','Hyper'), ('absent','Absent')
    ], default="na", string="RLQ", help="Right lower quadrant (RLQ) pain is tummy (abdominal) pain that is mainly in the lower half on the right-hand side.")

    #Umbilicus
    pe_git_visual = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('moist','Moist'),
        ('flare','Flare'), ('bleeding','Bleeding')
    ], default="na", string="Umbilicus Visual", help="the depression in the center of the surface of the abdomen indicating the point of attachment of the umbilical cord to the embryo; navel.")

    #Anus
    pe_git_palpitation = fields.Selection([('na','N/A'),
        ('patent','Patent'), ('imperforate','Imperforate'),
    ], default="na", string="Anus Palpitation")

    #Bowel
    pe_git_movements = fields.Selection([('na','N/A'),
        ('nausea','Nausea'), ('vomiting','Vomiting'),
        ('diarrhea','Diarrhea'), ('constipation','Constipation')
    ], default="na", string="Bowel Movements")

    #NEUROLOGICAL
    #LOC
    pe_nuerological_alertness = fields.Selection([('na','N/A'),
        ('alert','Alert'), ('Awake','Awake'),
        ('lethargic','Lethargic'), ('obtumded','Obtumded'),
        ('confused','Confused'), ('coma','Coma'),
        ('decerebrate','Decerebrate'), ('decorticate','Decorticate')
    ], default="na", string="Alertness", help="Alertness is the state of active attention by high sensory awareness such as being watchful and prompt to meet danger or emergency, or being quick to perceive and act.")

    #Orientation Level
    pe_nuerological_orientation_level = fields.Selection([('na','N/A'),
        ('person','Person'), ('place','Place'), ('time','Time'), 
        ('event','Event'), ('touch_voice','Response to touch and voice')
    ], default="na", string="Orientation Level", help="Orientation is something healthcare providers check when screening for dementia and evaluating cognitive abilities.")

    #Cranial Nerve
    pe_nuerological_sensory = fields.Selection([('na','N/A'),
        ('intact','Intact'), ('non_intact','Non-intact'),
    ], default="na", string="Sensory/Motor", help="Sensory level is defined as the lowest spinal cord level that still has normal pinprick and touch sensation.")

    #Pain level
    pe_nuerological_pain_level = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('severe','Severe'), ('low','Low')
    ], default="na", string="Nuerological Pain Level", help="These pain intensity levels may be assessed upon initial treatment, or periodically after treatment.")

    #GENITO URINARY
    pe_urinary_symptomps = fields.Selection([('na','N/A'),
        ('no','NO'), ('yes','YES')
    ], default="na", string="Signs and Symptoms of Infection")
    pe_urinary_symptomps_comment = fields.Char(string="Signs and Symptoms of Infection Describe", help="A symptom is a manifestation of disease apparent to the patient himself, while a sign is a manifestation of disease that the physician perceives.")

    pe_urinary_discharge = fields.Selection([('na','N/A'),
        ('no','NO'), ('yes','YES')
    ], default="na", string="Discharge", help=" Discharge can be normal or a sign of disease. Discharge also means release of a patient from care.")
    pe_urinary_discharge_comment = fields.Char(string="Discharge Describe")

    pe_urinary_genitalia_male = fields.Selection([('na','N/A'),
        ('testes_descended','Testes Descended'), ('undescended','Undescended'),
        ('hernia','Hernia'), ('hypospadias','Hypospadias')
    ], default="na", string="Genitalia Male", help="The genital organs of the male.")
    pe_urinary_genitalia_female = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('ambiguous','Ambiguous')
    ], default="na", string="Urinary Genitalia Female")

    #EXTREMITIES
    pe_extremities_arms = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('not_moving','Not Moving'), ('fracture','Fracture')
    ], default="na", string="Extremities Genitalia Female")
    pe_extremities_palmar_creases = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('single_crease','Single Crease')
    ], default="na", string="Palmar Creases", help="A crease or line on the palm. Supplement.")
    pe_extremities_fingers = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('polydactyl','Polydactyl'), 
        ('syndactyl','Syndactyl'), ('extra_fingers','Extra Fingers')
    ], default="na", string="Fingers", help="A finger is a limb of the human body and a type of digit, an organ of manipulation and sensation found in the hands of humans and other primates.")
    pe_extremities_hips = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('dislocated','Dislocated'), ('dislocatable','Dislocatable')
    ], default="na", string="Hips")
    pe_extremities_legs = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('not_moving','Not Moving')
    ], default="na", string="Legs")
    pe_extremities_feet_position = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('positional_deformity','Positional Deformity'),
        ('clubbed','Clubbed')
    ], default="na", string="Feet position")
    pe_extremities_toes = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('polydactyl','Polydactyl'), ('syndactyl','Syndactyl')
    ], default="na", string="Toes", help="Toes are the digits of the foot. The toe refers to part of the human foot, with five toes present on each human foot.")
    pe_extremities_back = fields.Selection([('na','N/A'),
        ('normal','Normal'), ('scoliosis','Scoliosis'),
        ('meningocele','Meningocele'), ('sacral_dimple','Sacral Dimple'),
        ('tuft_of_hair','Tuft of Hair')
    ], default="na", string="Back")


class HmsVitalSymptom(models.Model):
    _name = 'hms.vital.symptom'
    _description = 'Review of Systems Symptom'
    _order = 'category, sequence, name'

    name = fields.Char(required=True)
    category = fields.Selection([
        ('head_neck', 'Head and Neck'),
        ('ent', 'ENT'),
        ('eye', 'Eye'),
        ('chest_heart', 'Chest & Heart'),
        ('git', 'GIT'),
        ('surgery', 'Surgery'),
        ('urinary_gynec', 'Urinary & Gynecology'),
        ('ortho_neuro', 'Orthopedic & Neuro'),
        ('mouth', 'Mouth'),
        ('skin', 'Skin'),
        ('misc', 'Miscellaneous'),
    ], required=True, index=True)
    description = fields.Text()
    sequence = fields.Integer(default=10)