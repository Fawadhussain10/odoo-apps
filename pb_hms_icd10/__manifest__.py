# -*- coding: utf-8 -*-
#CODE Reference taken from GNU HEALTH for disease and category.
{
    'name' : 'International Classification of Diseases (ICD10)',
    'summary': 'International Classification of Diseases and Diseases Category (ICD10).',
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'license': 'OPL-1',
    'depends' : ['pb_hms'],
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'description': """
        International Classification of Diseases, PackBytes pb hms icd10 hospital management system.
    """,
    'images': ['static/description/banner.png'],
    "data": [
        "data/disease_categories.xml",
        "data/diseases.xml",
    ],
    "cloc_exclude": [
        "data/*.xml",
    ],
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 15,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: