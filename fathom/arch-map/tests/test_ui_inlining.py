"""Interface tests for the **MCP-App Resources & Asset Inlining** module (server.py).

The MCP-App sandbox cannot fetch /assets/*, so _inline_app rewrites the studio's
external <link>/<script> tags into inline <style>/<script> blocks and flips the
page into host mode by injecting window.__ARCH_APP__ before any script runs.
studio_ui / view_ui are the pre-declared MCP-App resources serving that HTML.
"""
import arch_map.server as srv


def test_inline_app_inlines_assets_and_flips_host_mode():
    html = srv._inline_app(srv.STUDIO_INDEX)
    assert '<link rel="stylesheet" href="/assets/' not in html   # CSS inlined
    assert '<script src="/assets/' not in html                   # local JS inlined
    assert "<style>" in html and "<script>" in html
    assert "window.__ARCH_APP__ = true" in html                  # host-mode flag
    assert html.index("window.__ARCH_APP__") < html.index("</head>")


def test_studio_ui_and_view_ui_serve_inlined_pages():
    assert "window.__ARCH_APP__ = true" in srv.studio_ui()
    assert "window.__ARCH_APP__ = true" in srv.view_ui()
