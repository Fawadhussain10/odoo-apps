{
    'name': 'POS - Hide Tax on Receipt',
    'category': 'Point of Sale',
    'summary': """Hide the tax breakdown (untaxed subtotal + tax lines) on the POS receipt while keeping tax recorded in the backend.
                keywords: hide tax receipt | POS receipt no tax | hide untaxed amount | receipt total only""",
    'description': """
        Hides the tax details section on the POS customer receipt.

        Tax is still calculated, applied and recorded on the order (and in
        accounting) exactly as before. Only the visual breakdown on the printed
        receipt is removed:

        - The "Subtotal" (untaxed amount) line is hidden.
        - The per-tax-group tax lines are hidden.
        - The final "Total" line remains and shows the full amount the customer
          pays (tax included).
    """,
    'author': 'Fawad Hussain',
    'support': 'fawadh817@gmail.com',
    'version': '19.0.1.0.0',
    'price': 10.00,
    'currency': 'EUR',
    'depends': ['point_of_sale'],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_hide_receipt_tax/static/src/**/*',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
