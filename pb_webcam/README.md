# Instructions for Adding Gantt view

You can add pb.webcam.mixin in your custom model and add pb_webcam_url in view and it will work without any further changes.

EG:

In PY
------
class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner','pb.webcam.mixin']

    def pb_webcam_retrun_action(self):
        self.ensure_one()
        return self.env.ref('pb_hms_base.action_patient').id
        (Action of your object)

in View
---------
    <field name="pb_webcam_url" widget="webcam_redirect_button"/>

For updating image on any custom field you can set call it using following url
-----
web_base_url + '/pb/webcam/' + model_name + '/' + str(record_id) '/' + str(field_name)

EG: https://www.packbytes.com/pb/webcam/hms.patient/5/new_field 