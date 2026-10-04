import logging

from odoo.addons.fbr_integration_multicompany.models.fbr_api import SALE_TYPE_SELECTION

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """sale_type changed from Char (FBR label text) to Selection (key): convert stored labels to keys."""
    for table in ('product_template', 'product_product', 'account_move_line'):
        cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = 'sale_type'", (table,))
        if not cr.fetchone():
            continue
        for key, label in SALE_TYPE_SELECTION:
            cr.execute(
                f"UPDATE {table} SET sale_type = %s WHERE lower(trim(sale_type)) IN (lower(%s), %s)",
                (key, label, key),
            )
        # unknown values are cleared; drop NOT NULL first, the ORM restores it (filling the default) afterwards
        cr.execute(f"ALTER TABLE {table} ALTER COLUMN sale_type DROP NOT NULL")
        cr.execute(
            f"UPDATE {table} SET sale_type = NULL WHERE sale_type IS NOT NULL AND sale_type NOT IN %s RETURNING id",
            (tuple(key for key, _label in SALE_TYPE_SELECTION),),
        )
        cleared = [row[0] for row in cr.fetchall()]
        if cleared:
            _logger.warning("fbr_integration_multicompany: cleared unknown sale_type on %s ids %s", table, cleared)
