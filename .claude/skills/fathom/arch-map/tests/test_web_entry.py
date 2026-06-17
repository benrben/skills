"""Interface tests for the **web entrypoint** (web.py).

python -m arch_map.web runs the SAME FastMCP instance as the stdio entrypoint
over HTTP, and its banner must point a human at the studio root (not /mcp,
which 406s a plain browser GET).
"""
import arch_map.web as web


def test_web_main_prints_studio_url_and_serves_http(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(web.mcp, "run", lambda **kw: calls.append(kw))
    web.main()
    out = capsys.readouterr().out
    assert "arch-map studio" in out
    assert f"http://{web.HOST}:{web.PORT}/" in out
    assert calls == [{"transport": "http", "host": web.HOST, "port": web.PORT}]
