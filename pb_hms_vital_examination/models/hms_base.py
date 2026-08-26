# -*- encoding: utf-8 -*-
from odoo import api, fields, models,_

class Appointment(models.Model):
    _inherit = "hms.appointment"

    READONLY_STATES = {'cancel': [('readonly', True)], 'done': [('readonly', True)]}

    # Head and Neck
    vs_headaches = fields.Boolean(string="Headache", help='A painful sensation in any part of the head, ranging from sharp to dull, that may occur with other symptoms.')
    vs_migraine = fields.Boolean(string="Migraine", help='A migraine is a headache that can cause severe throbbing pain or a pulsing sensation, usually on one side of the head. It is often accompanied by nausea, vomiting, and extreme sensitivity to light and sound.')
    vs_neck_pain = fields.Boolean(string="Neck Pain", help='Pain in the neck and shoulder that varies in intensity, and may feel achy or like an electric shock from the neck to the arm.')
    vs_limited_neck_movements = fields.Boolean(string="Limited Neck Movements", help='Impaired or limited neck flexion has a variety of causes and usually involves actions that require you to look down often.')
    vs_head_trauma = fields.Boolean(string="Head Trauma", help='Brain dysfunction caused by an outside force, usually a violent blow to the head.')
    vs_dizziness = fields.Boolean(string="Dizziness", help='Altered sense of balance and place, possibly described as lightheaded, feeling faint or as if head is spinning.')
    vs_drowsiness = fields.Boolean(string="Drowsiness", help='Strong desire for sleep and feeling of drowsiness.')
    vs_headedness = fields.Boolean(string="Headedness", help='Feeling dizzy or about to pass out.')
    vs_enlarged_cervical_ln = fields.Boolean(string="Enlarged Cervical LN", help='This article looks at the symptoms and causes of swollen lymph nodes in your neck.')
    vs_painful_cervical_ln = fields.Boolean(string="Painful cervical LN", help='Pain in the neck and shoulder that varies in intensity, and may feel achy or like an electric shock from the neck to the arm.')

    # ENT
    vs_earache = fields.Boolean(string="Earache", help='Pain in the inner or outer ear that may interfere with ability to hear, often caused by excess fluid and infection.')
    vs_tinnitus = fields.Boolean(string="Tinnitus", help='Ringing or buzzing noise in one or both ears that may be constant or come and go, often associated with hearing loss.')
    vs_low_hearing_equity = fields.Boolean(string="Low Hearing Equity", help='Hearing loss is common as we age but hearing aid use, the primary approach to managing hearing loss, is not. Nationally, only about 15-20% of older adults with hearing loss use hearing aids.')
    vs_clogged_ears = fields.Boolean(string="Clogged Ears", help="Ear pain can have causes that are't due to underlying disease.")
    vs_lot_of_ear_wax = fields.Boolean(string="Lot Of EarWax", help='People who produce a lot of earwax are more likely to have an earwax blockage and impaction, which is where the wax gets pushed deep inside the ear canal.')
    vs_runny_nose = fields.Boolean(string="Runny Nose", help='Excess drainage, ranging from a clear fluid to thick mucus, from the nose and nasal passages.')
    vs_blocked_nose = fields.Boolean(string="Blocked Nose", help='Nasal passages swollen with excess fluid and mucus, may be triggered by infection, tobacco smoke or perfume.')
    vs_stuffy_nose = fields.Boolean(string="Stuffy Nose", help='Nasal passages swollen with excess fluid and mucus, may be triggered by infection, tobacco smoke or perfume.')
    vs_epistaxis = fields.Boolean(string="Epistaxis", help='Bleeding from the nose, either spontaneous or induced by nose picking or trauma.')
    vs_sneezing = fields.Boolean(string="Sneezing", help='A sudden blast of air or mucus expelled from the mouth and nose.')
    vs_sore_throat = fields.Boolean(string="Sore throat", help='Pain or irritation in the throat that can occur with or without swallowing, often accompanies infections, such as a cold or flu.')
    vs_itching_dry_throat = fields.Boolean(string="Itching Dry Throat", help='Dry throat is a rough, scratchy, sometimes itchy feeling in the throat.')
    vs_swallowing_pain = fields.Boolean(string="Swallowing pain", help='Pain when swallowing food or liquids.')
    vs_pharyngitis = fields.Boolean(string="Pharyngitis", help='Pain or irritation in the throat that can occur with or without swallowing, often accompanies infections, such as a cold or flu.')
    vs_tonsillitis = fields.Boolean(string="Tonsillitis", help='Tonsillitis is inflammation of the tonsils, two oval-shaped pads of tissue at the back of the throat — one tonsil on each side.')
    vs_rhinitis = fields.Boolean(string="Rhinitis", help='Irritation and swelling of the mucous membrane in the nose.')
    vs_sinusitis = fields.Boolean(string="Sinusitis", help='Sinusitis is an inflammation of the sinuses that can cause them to get blocked and filled with fluid. It is usually caused by cold or allergies.')
    vs_ear_drum_redness = fields.Boolean(string="Ear drum redness", help='Otitis externa is a condition that causes inflammation (redness and swelling) of the external ear canal, which is the tube between the outer ear and eardrum.')
    vs_painful_ear_auricle = fields.Boolean(string="Painful ear auricle", help='Outer ear pain can most commonly be caused by environmental conditions such as water exposure or extreme cold weather that can lead to frostbite of the outer ear.')
    vs_swollen_ear_lobule = fields.Boolean(string="Swollen ear lobule", help='Swelling can have causes that aren not due to underlying disease. ')
    vs_ear_rash = fields.Boolean(string="Ear rash", help='Different skin conditions, such as contact dermatitis and psoriasis, can cause rashes to appear behind the ears.')
    vs_post_nasal_drip = fields.Boolean(string="Postnasal drip", help='Secretions from the nose that drain down into the throat, causing congestion and cough. Postnasal drip is usually caused by allergies or the common cold.')
    vs_vertigo = fields.Boolean(string="Vertigo", help='A sudden internal or external spinning sensation, often triggered by moving your head too quickly.')
    vs_hearing_loss = fields.Boolean(string="Hearing loss", help='Total or significant loss of hearing.')

    # Eye
    vs_eye_redness = fields.Boolean(string="Eye redness", help='Eye redness from irritated or inflamed blood vessels on the surface of the white part of the eye, commonly called bloodshot eyes.')
    vs_conjunctivitis = fields.Boolean(string="Conjunctivitis", help='Inflammation or infection of the outer membrane of the eyeball and the inner eyelid.')
    vs_red_eye_lid = fields.Boolean(string="Red eyelid", help='Allergies, infections, and even crying can cause your eyelids to redden.')
    vs_swollen_eye_lid = fields.Boolean(string="Swollen eyelid", help='Eyelid swelling is the enlargement of either or both the lower and upper eyelids, on one or both eyes.')
    vs_eye_lid_pimple = fields.Boolean(string="Eyelid pimple", help='Most bumps on the eyelid are styes.')
    vs_squint = fields.Boolean(string="Squint", help='A squint, also called strabismus, is where the eyes point in different directions.')
    vs_low_visual_equity = fields.Boolean(string="Low visual equity", help='Here is one definition of low vision, related to visual acuity: Low vision is a condition caused by eye disease.')
    vs_lacrimation = fields.Boolean(string="Lacrimation", help='Tears are a clear liquid secreted by the lacrimal glands found in the eyes of all land mammals.')
    vs_dry_eye = fields.Boolean(string="Dry eye", help='Dry eye that occurs when tears are not able to provide adequate moisture.')
    vs_itching_eye = fields.Boolean(string="Itching eye", help='The most common cause of itchy eyes is an allergy. Itchy eyes can be triggered by exposure to pollen, animal fur, mould, dust mites, make-up or eye drops')
    vs_painful_eye = fields.Boolean(string="Painful eye", help='Eye pain can have causes that are not due to underlying disease.')
    vs_eye_secretions = fields.Boolean(string="Eye secretions", help='Eye discharge primarily consists of thin, watery mucus produced by the conjunctiva (called mucin), and meibum — an oily substance secreted by the meibomian glands which helps keep your eyes lubricated between blinks.')
    vs_swollen_eye = fields.Boolean(string="Swollen eye", help='The most common cause of eyelid swelling is allergies, either by direct contact with the allergen or from a systemic allergic reaction.')
    vs_eye_skin_color_change = fields.Boolean(string="Eye skin color change", help='Dark eyelids occur when the skin surrounding the upper eye region darkens in color.')

    # Chest & Heart
    vs_chest_tightness = fields.Boolean(string="Chest tightness", help='Chest tightness describes any discomfort that occurs between your lower neck and upper belly area. Tightness in the chest may be felt all over the chest area or located in one spot or several spots in the chest. Chest tightness can occur in any age group.')
    vs_chest_compression = fields.Boolean(string="Chest compression", help="Chest compression is the act of applying pressure to someone's chest in order to help blood flow through the heart in an emergency situation. Give one breath of mouth-to-mouth resuscitation, followed by five chest compressions.")
    vs_shortness_of_breath = fields.Boolean(string="Shortness of breath", help='Difficult or laboured breathing.')
    vs_dyspnea = fields.Boolean(string="Dyspnea", help='Dyspnea, also called shortness of breath, is a tight feeling in your chest where you may not be able to take a deep breath.')
    vs_wet_cough = fields.Boolean(string="Wet cough", help="A wet cough, also known as a productive cough, is any cough that produces mucus (phlegm). It may feel like you have something stuck in your chest or the back of your throat.")
    vs_yellow_green_phlegm = fields.Boolean(string="Yellow, green phlegm", help="Phlegm is a type of mucus made in your chest. You typically don’t produce noticeable amounts of phlegm unless you are sick with a cold or have some other underlying medical issue.")
    vs_hemoptysis = fields.Boolean(string="Hemoptysis", help="Small amounts of blood mixed with sputum (or more seriously, large amounts of bright red blood) brought up by a forceful cough.")
    vs_wheezy_chest = fields.Boolean(string="Wheezy chest", help="Wheezing is usually caused by an obstruction (blockage) or narrowing of the small bronchial tubes in the chest.")
    vs_chest_crepitation = fields.Boolean(string="Chest crepitation", help="Bibasilar crackles are a bubbling or crackling sound originating from the base of the lungs. They may occur when the lungs inflate or deflate.")
    vs_chest_crackles = fields.Boolean(string="Chest crackles", help="Bibasilar crackles are abnormal sounds from the base of the lungs.")
    vs_chest_deformity = fields.Boolean(string="Chest deformity", help="A chest wall deformity is a structural abnormality of the chest that can range from mild to severe.")
    vs_palpitations = fields.Boolean(string="Chest & Heart Palpitations", help="A sensation that the heart is racing, pounding, fluttering or skipping a beat, often bothersome, but hardly ever a sign of heart disease.")
    vs_heart_murmurs = fields.Boolean(string="Heart murmurs", help="Sound of blood flowing through the heart, due to anything from healthy heart exertion during exercise to a diseased heart valve or other abnormality.")
    vs_orthopnea = fields.Boolean(string="Orthopnea", help="Orthopnea is a shortness of breath that affects a person when they are lying down but subsides in other positions, such as standing or sitting up.")
    vs_cardio_thoracic_scar = fields.Boolean(string="Cardio-thoracic scar", help="relating to, involving, or specializing in the heart and chest cardiothoracic surgery.")
    vs_dry_cough = fields.Boolean(string="Dry Cough", help="A nonproductive cough, also known as a dry cough, doesn't produce phlegm or mucus.")

    # GIT
    vs_epigastric_pain = fields.Boolean(string="Epigastric pain", help="Epigastric pain is a name for pain or discomfort right below your ribs in the area of your upper abdomen.")
    vs_heartburn = fields.Boolean(string="Heartburn", help="Heartburn is a symptom of a common medical condition (GERD) that affects up to 20% of the population.")
    vs_gastric_regurgitation = fields.Boolean(string="Gastric regurgitation", help="Gastroesophageal reflux disease (GERD) occurs when stomach acid frequently flows back into the tube connecting your mouth and stomach.")
    vs_right_upper_quadrant_pain = fields.Boolean(string="Right upper quadrant pain", help="Right upper quadrant (RUQ) pain is a common complaint that typically stimulates a workup of the hepatobiliary system.")
    vs_left_upper_quadrant_pain = fields.Boolean(string="Left upper quadrant pain", help="Left upper quadrant (RUQ) pain is a common complaint that typically stimulates a workup of the hepatobiliary system.")
    vs_right_lower_quadrant_pain = fields.Boolean(string="Right lower quadrant pain", help="Right lower quadrant (RUQ) pain is a common complaint that typically stimulates a workup of the hepatobiliary system.")
    vs_left_lower_quadrant_pain = fields.Boolean(string="Left lower quadrant pain", help="Left lower quadrant (RUQ) pain is a common complaint that typically stimulates a workup of the hepatobiliary system.")
    vs_para_umbilical_pain = fields.Boolean(string="Para-umbilical pain", help="Periumbilical pain is a type of abdominal pain that is localized in the region around or behind your belly button.")
    vs_distention = fields.Boolean(string="Distention", help="The state of being distended, enlarged, swollen from internal pressure. For example, on inhalation there is distention of the lungs due to the increased air pressure within the lungs")
    vs_diarrhea = fields.Boolean(string="Diarrhea", help="loose, watery and possibly more-frequent bowel movements — is a common problem.")
    vs_constipation = fields.Boolean(string="Constipation", help="Chronic constipation is infrequent bowel movements or difficult passage of stools that persists for several weeks or longer.")
    vs_abdominal_gases = fields.Boolean(string="Abdominal Gases", help="Intestinal gas, a buildup of air in the digestive tract, is usually not noticed until you burp or pass it rectally.")
    vs_abdominal_scar = fields.Boolean(string="Abdominal scar", help="Abdominal adhesions are scar tissue that forms between abdominal tissues and organs that causes your tissues and organs to stick together.")
    vs_blood_in_stool = fields.Boolean(string="Blood in stool", help="Hematochezia and melena both refer to having blood in your stool. While hematochezia causes bright red blood to appear in or around your stool, melena causes dark stools that often feel sticky.")
    vs_abdominal_pain = fields.Boolean(string="Abdominal Pain", help="Abdominal pain can be referred to as visceral pain or peritoneal pain. The contents of the abdomen can be divided into the foregut, midgut, and hindgut.")
    vs_nausea = fields.Boolean(string="Nausea", help="Stomach queasiness, the urge to vomit. Nausea can be brought on by many causes, including systemic illnesses, medications, pain, and inner ear disease.")
    vs_vomiting = fields.Boolean(string="Vomiting", help="The act of vomiting is also called emesis. From the Indo-European root wem- (to vomit), the source of the words such as emetic and wamble.")


    # Surgery
    vs_hemorrhoids = fields.Boolean(string="Hemorrhoids(Piles)", help="Hemorrhoids (HEM-uh-roids), also called piles.")
    vs_anal_fissures = fields.Boolean(string="Anal fissures", help="An anal fissure is a small tear in the thin, moist tissue (mucosa) that lines the anus.")
    vs_gluteal_pimple = fields.Boolean(string="Gluteal pimple", help="What people refer to as butt acne is typically a different condition. The medical term is folliculitis. Folliculitis affects the hair follicles rather than the pores of the skin.")
    vs_abscess = fields.Boolean(string="Abscess", help="A local accumulation of pus anywhere in the body.")
    vs_pimples = fields.Boolean(string="Pimples", help="This is the medical term for acne, or pimples.")
    vs_cut_wound = fields.Boolean(string="Cut wound", help="A cut is a break or opening in the skin. It is also called a laceration. A cut may be deep, smooth, or jagged. It may be near the surface of the skin, or deeper.")
    vs_surgical_wound = fields.Boolean(string="Surgical wound", help="An incision is a cut through the skin that is made during surgery. It is also called a surgical wound.")
    vs_bedsores = fields.Boolean(string="Bedsores", help="Bedsores are ulcers that happen on areas of the skin that are under pressure from lying in bed, sitting in a wheelchair, or wearing a cast for a prolonged time.")
    vs_diabetic_foot = fields.Boolean(string="Diabetic foot", help="Diabetic foot is a condition in which foot ulcers form on patients with diabetes. People with diabetic foot ulcers (DFUs) have a decreased quality of life and an 8% higher incidence of needing a lower extremity amputation (LEA) in the future.")
    vs_varicose_veins = fields.Boolean(string="Varicose veins", help=" A vein that has enlarged and twisted, often appearing as a bulging, blue blood vessel that is clearly visible through the skin.")
    vs_cesarean_section = fields.Boolean(string="Cesarean section", help="Cesarean delivery (C-section) is a surgical procedure used to deliver a baby through incisions in the abdomen and uterus.")
    vs_furuncles = fields.Boolean(string="Furuncles", help="“Furuncle” is another word for a “boil.” Boils are bacterial infections of hair follicles that also involve the surrounding tissue.")

    # Urinary & gynecology
    vs_renal_colic = fields.Boolean(string="Renal colic", help="Renal colic is a type of pain you get when urinary stones block part of your urinary tract.")
    vs_loin_pain = fields.Boolean(string="Loin pain", help="which is a medical term for blood in the urine.")
    vs_dysuria = fields.Boolean(string="Dysuria", help="Dysuria means you feel pain or a burning sensation when you pee.")
    vs_frequency = fields.Boolean(string="Frequency", help="The number of occurrences of a periodic or recurrent process in a unit of time, such as the number of electrical cycles per second measured in hertz.")
    vs_urgency = fields.Boolean(string="Urgency", help="Urgency is an abrupt, strong, often overwhelming, need to urinate.")
    vs_lower_middle_abdominal_pain = fields.Boolean(string="Lower middle abdominal pain", help="Everyone experiences abdominal pain from time to time. Other terms used to describe abdominal pain are stomachache, tummy ache, gut ache and bellyache.")
    vs_dark_urine = fields.Boolean(string="Dark urine", help="This condition is called rhabdomyolysis, and it can turn your urine brown. If you have brown urine because of rhabdo, you might also notice: Muscle pain. Muscle weakness.")
    vs_cutting_urination = fields.Boolean(string="Cutting urination")
    vs_bloody_urine = fields.Boolean(string="Bloody urine", help="Blood in the urine may range from very obvious to microscopic and not visible at all.")
    vs_dysmenorrhea = fields.Boolean(string="Dysmenorrhea", help="Cramps and pelvic pain with menstruation, with common causes such as heavy flow, passing clots, uterine fibroids or endometriosis.")
    vs_hemorrhagia = fields.Boolean(string="Hemorrhagia", help="The release of blood from a broken blood vessel, either inside or outside the body.")
    vs_missed_pills = fields.Boolean(string="Missed pills", help="A combination pill is “missed” if you do not take it for 24 or more hours after you were supposed to. In other words, you've only technically missed a pill, if it's been more than 48 hours since your last active pill.")
    vs_irregular_menstruation = fields.Boolean(string="Irregular menstruation", help="Missed, delayed or erratic periods or abnormal bleeding patterns.")

    # Orthopedic & Neuro
    vs_fatigue = fields.Boolean(string="Fatigue", help="Feeling overtired, with low energy and a strong desire to sleep that interferes with normal daily activities.")
    vs_general_weakness = fields.Boolean(string="General weakness", help="Asthenia, also known as weakness, is the feeling of body fatigue or tiredness. A person experiencing weakness may not be able to move a certain part of their body properly.")
    vs_low_energy = fields.Boolean(string="Low energy", help="Fatigue is a feeling of weariness, tiredness, or lack of energy")
    vs_general_body_aches = fields.Boolean(string="General body aches")
    vs_muscle_pain = fields.Boolean(string="Muscle pain", help="The medical term for muscle pain is myalgia. Myalgia can be described as muscle pains, aches, and pain associated with ligaments, tendons, and the soft tissues that connect bones, organs, and muscles.")
    vs_low_back_pain = fields.Boolean(string="Low back pain", help="Low back pain (LBP) or lumbago is a common disorder involving the muscles, nerves, and bones of the back. Pain can vary from a dull constant ache to a sudden sharp feeling.")
    vs_upper_back_pain = fields.Boolean(string="Upper back pain", help="Upper back pain occurs in the thoracic spine, which is often described as the upper back, middle back, or mid-back.")
    vs_shoulder_pain = fields.Boolean(string="Shoulder pain", help="Physical discomfort of the shoulder, including the joint itself or the muscles, tendons and ligaments that support the joint.")
    vs_lower_limb_pain = fields.Boolean(string="Lower limb pain", help="Most leg pain results from wear and tear, overuse, or injuries in joints or bones or in muscles, ligaments, tendons or other soft tissues.")
    vs_hip_joint_pain = fields.Boolean(string="Hip joint pain", help="Physical discomfort in the hip, which varies from mild to severe.")
    vs_knee_joint_pain = fields.Boolean(string="Knee joint pain", help="Pain in or around the knee that may indicate a condition affecting the knee joint itself or the soft tissue around the knee.")
    vs_elbow_joint_pain = fields.Boolean(string="Elbow joint pain", help="Elbow pain can have causes that aren't due to underlying disease. Examples include prolonged pressure or leaning on elbows, trying a new exercise such as tennis, local trauma, desk work, sprains or strains.")
    vs_ankle_joint_pain = fields.Boolean(string="Ankle joint pain", help="Ankle pain can have causes that aren't due to underlying disease. Examples include poorly fitting footwear such as ski boots, high heels, sprains, strains, overuse, lack of use or trauma.")
    vs_ankle_twist = fields.Boolean(string="Ankle twist", help="An injury that occurs when the ankle rolls, twists or turns in an awkward way.")
    vs_joint_swelling = fields.Boolean(string="Joint swelling", help="joints swelling happen when there's an increase of fluid in the tissues that surround the joints. Joint swelling is common with different types of arthritis, infections, and injuries.")
    vs_foot_oedema = fields.Boolean(string="Foot oedema", help="standing or sitting in the same position for too long.")
    vs_lowe_limb_oedema = fields.Boolean(string="Lower limb oedema", help="Lower limb edema is a common and challenging diagnostic problem often with a significant impact. It is defined as swelling caused by an increase in interstitial fluid that exceeds the capacity of physiologic lymphatic drainage.")
    vs_numbness = fields.Boolean(string="Numbness", help="Numbness is a loss of feeling or sensation in an area of the body.")
    vs_tingling = fields.Boolean(string="Tingling", help="Tingling (paresthesia) is an unusual sensation most commonly felt in your hands, feet, arms and legs")
    vs_paresthesia = fields.Boolean(string="Paresthesia", help="Paresthesia is numbness or a burning feeling that occurs most often in the extremities, such as the hands, arms, legs, or feet, but that can happen elsewhere in the body as well. It is the same “pins and needles” feeling that happens when someone sits on their leg or foot for too long.")
    vs_neuropathic_pain = fields.Boolean(string="Neuropathic pain", help="Neuropathic pain can happen if your nervous system is damaged or not working correctly.")
    vs_weak_reflexes = fields.Boolean(string="Weak reflexes", help="When reflex responses are absent this could be a clue that the spinal cord, nerve root, peripheral nerve, or muscle has been damaged.")
    vs_limitation_of_movements = fields.Boolean(string="Limitation of movements", help="The restriction of movement or range of motion of a part or joint, esp. that imposed by disease or trauma to joints and soft tissues.")
    vs_psychic_trauma = fields.Boolean(string="Psychic trauma", help="psychic trauma a psychologically upsetting experience that produces an emotional or mental disorder or otherwise has lasting negative effects on a person's thoughts, feelings, or behavior.")
    vs_general_anxiety = fields.Boolean(string="General anxiety", help="Generalized anxiety is a mental disorder in which a person is often worried or anxious about many things and finds it hard to control this anxiety.")
    vs_hemiplegia = fields.Boolean(string="Hemiplegia", help="Hemiplegia (sometimes called hemiparesis) is a condition, caused by a brain injury, that results in a varying degree of weakness, stiffness (spasticity) and lack of control in one side of the body.")
    vs_paraplegia = fields.Boolean(string="Paraplegia",help="Paralysis of the lower half of your body, including both legs, is called paraplegia. Paralysis of the arms and legs is quadriplegia.")
    vs_quadriplegia = fields.Boolean(string="Quadriplegia")
    vs_depression_red_flag = fields.Boolean(string="Depression red flag", help="Aches and pains – Experiencing headaches, muscle pain or stomach aches for no reason.")
    vs_autistic_red_flag = fields.Boolean(string="Autistic red flag")

    # Mouth
    vs_mouth_sores = fields.Boolean(string="Mouth sores", help="One or more painful sores on inner lips, gums, tongue, roof of the mouth or throat that may interfere with eating, such as a canker sore.")
    vs_tongue_sores = fields.Boolean(string="Tongue sores", help="Inflammation of the tongue is medically known as glossitis.")
    vs_oral_blisters = fields.Boolean(string="Oral blisters", help="Mouth ulcers — also known as canker sores — are normally small, painful lesions that develop in your mouth or at the base of your gums.")
    vs_white_colored_tongue = fields.Boolean(string="White colored tongue", help="White tongue is the result of an overgrowth and swelling of the fingerlike projections (papillae) on the surface of your tongue.")
    vs_strawberry_tongue = fields.Boolean(string="Strawberry tongue", help="a tongue that is red from swollen congested papillae and that occurs especially in scarlet fever and Kawasaki disease.")
    vs_geographic_tongue = fields.Boolean(string="Geographic tongue", help="Geographic tongue results from the loss of tiny hairlike projections (papillae) on your tongue's surface.")
    vs_oral_white_patches = fields.Boolean(string="Oral white patches", help="Leukoplakia appears as thick, white patches on the inside surfaces of your mouth. It has a number of possible causes, including repeated injury or irritation.")
    vs_teething = fields.Boolean(string="Teething", help="Teething is the emergence of the primary (baby) teeth through a baby or child's gums.")
    vs_dental_pain = fields.Boolean(string="Dental pain", help="Dental pain, also known as Toothache, is pain in the teeth or their supporting structures, caused by dental diseases or pain referred to the teeth by non-dental diseases.")
    vs_toothache = fields.Boolean(string="Toothache", help="Toothache, also known as dental pain, is pain in the teeth or their supporting structures, caused by dental diseases or pain referred to the teeth by non-dental diseases.")
    vs_dental_cares = fields.Boolean(string="Dental cares", help="Dental caries or cavities, more commonly known as tooth decay, are caused by a breakdown of the tooth enamel.")
    vs_oral_bad_odor = fields.Boolean(string="Oral bad odor", help="Halitosis is an oral health problem where the main symptom is bad smelling breath.")
    vs_mouth_angles_fissures = fields.Boolean(string="Mouth angles fissures", help="Angular cheilitis is a condition that causes red, swollen patches in the corners of your mouth where your lips meet and make an angle.Other names for it are perleche and angular stomatitis.")
    
    # Skin 
    vs_skin_rash = fields.Boolean(string="Skin rash", help="Medically, a rash is referred to as an exanthem.")
    vs_blisters = fields.Boolean(string="Blisters", help="A collection of fluid underneath the top layer of skin (epidermis).")
    vs_red_patches = fields.Boolean(string="Red patches")
    vs_dry_skin = fields.Boolean(string="Dry skin", help="Dry skin occurs when your skin loses too much water and oil. Dry skin is common and can affect anyone at any age. The medical term for dry skin is xerosis.")
    vs_fissured_skin = fields.Boolean(string="Fissured skin", help="Skin fissures are cracks in the skin that form due to intense dryness and thickened skin.")
    vs_redness = fields.Boolean(string="Redness", help="Redness of the skin that results from capillary congestion. Erythema can occur with inflammation, as in sunburn and allergic reactions to drugs.")
    vs_itching = fields.Boolean(string="Itching", help="Itching is medically known as pruritis; something that is itchy is pruritic.")
    vs_burns = fields.Boolean(string="Burns", help="Burns are tissue damage that results from heat, overexposure to the sun or other radiation, or chemical or electrical contact.")
    vs_scars = fields.Boolean(string="Scars", help="The fibrous tissue replacing normal tissues destroyed by injury or disease. Sometimes called cicatrix.")
    vs_hair_loss = fields.Boolean(string="Hair loss", help=" Loss of hair as a result of illness, functional disorder, or hereditary disposition.")
    vs_hair_cracking = fields.Boolean(string="Hair cracking", help="stress fracture. (redirected from Hairline crack)")
    vs_nails_cracking = fields.Boolean(string="Nails cracking", help="A split nail is usually caused by physical stress, nutrient deficiency, or wear and tear. Split nails can be a problem, especially if you work with your hands.")
    vs_nails_fungal_infection = fields.Boolean(string="Nails fungal infection")
    vs_over_sweating = fields.Boolean(string="Over sweating", help="Hyperhidrosis is a medical condition in which a person sweats excessively and unpredictably.")
    vs_skin_crackles = fields.Boolean(string="Skin crackles", help="Crepitus is grating, crackling or popping sounds and sensations experienced under the skin and joints or a crackling sensation due to the presence of air in the subcutaneous tissue.")
    vs_lips_fissures = fields.Boolean(string="Lips fissures")
    vs_swollen_lips = fields.Boolean(string="Swollen lips")

    # Miscellaneous
    vs_general_checkup = fields.Boolean(string="General checkup", help=" a medical examination to test your general state of health")
    vs_new_born_baby_checkup = fields.Boolean(string="New born baby checkup", help="Taking your baby for regular medical checkups can help keep your baby healthy. ")
    vs_preschool_checkup = fields.Boolean(string="Preschool checkup")
    vs_laboratory_checkup = fields.Boolean(string="Laboratory checkup", help="A medical procedure that involves testing a sample of blood, urine, or other substance from the body.")
    vs_teleconsultation = fields.Boolean(string="Teleconsultation", help="Teleconsultation, sometimes referred to as remote consultation or telehealth, refers to interactions that happen between a clinician and a patient for the purpose of providing diagnostic or therapeutic advice through electronic means.")
    vs_second_opinion_consultation = fields.Boolean(string="Second opinion consultation", help="In medicine, the opinion of a doctor other than the patient's current doctor. ... A second opinion may confirm or question the first doctor's diagnosis and treatment plan, give more information about the patient's disease or condition, and offer other treatment options.")
    vs_referral_request = fields.Boolean(string="Referral request", help="A written order from your primary care doctor for you to see a specialist or get certain medical services.")
    vs_sick_leave_request = fields.Boolean(string="Sick leave request", help="an absence from work permitted because of illness.")
    vs_medical_certificate_request = fields.Boolean(string="Medical certificate request", help="A medical certificate or doctor's certificate is a written statement from a physician or another medically qualified health care provider which attests to the result of a medical examination of a patient.")
    vs_medical_advice_request = fields.Boolean(string="Medical advice request", help="Guidance or recommendations from a doctor, nurse, or other healthcare professional regarding a person's health or fitness. 'seek medical advice in the event of further symptoms'")

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