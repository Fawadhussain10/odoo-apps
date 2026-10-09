"""Start the LinkedIn engine with Odoo's extra tools, run with the engine's own Python.

The engine is the unmodified linkedin-mcp-server (Apache-2.0, see NOTICE).

The engine registers its tools in linkedin_mcp_server.server; the post tools
Odoo needs (create_post, get_post_stats, engine/odoo_tools.py) are added right
after the engine's own post tools, inside the same browser-driving gate, so
they share the browser session and run one at a time with the others.
connect_with_person is wrapped in memory to report LinkedIn's own notice when
an invitation is not recorded (odoo_tools.install_invite_notices).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import linkedin_mcp_server.server as engine_server  # noqa: E402

from odoo_tools import install_invite_notices, register_odoo_tools  # noqa: E402

_register_post_tools = engine_server.register_post_tools


def register_post_tools(mcp, **kwargs):
    _register_post_tools(mcp, **kwargs)
    register_odoo_tools(mcp, tool_timeout=kwargs.get('tool_timeout', 180.0))


engine_server.register_post_tools = register_post_tools
install_invite_notices()

from linkedin_mcp_server.cli_main import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
