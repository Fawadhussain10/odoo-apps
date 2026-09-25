# -*- coding: utf-8 -*-

# The account() route override that used to live here duplicated Odoo's own
# /my/account form-save logic (MANDATORY_BILLING_FIELDS/OPTIONAL_BILLING_FIELDS,
# manual image_1920 handling) against the pre-19 portal_my_details template.
# Odoo 19 replaced that whole flow with a new address-form system
# (portal.address_form_fields, /my/address/submit) that this override doesn't
# match at all, so it's removed - native Odoo 19 /my/account behavior applies
# unchanged. The profile photo still displays in the portal layout via
# views/template.xml; portal users just can't upload their own photo from
# My Details anymore.
