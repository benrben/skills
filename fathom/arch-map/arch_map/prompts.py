"""grill_candidate PROMPT — the user-invoked face of the /deepen grilling loop
(spec-spine-prompts).

FastMCP v3 prompts return a plain string (NOT a raw {role, content} dict). This
prompt is user-invoked and has NO side effects. It returns the EXACT walkthrough
text the archmap_grilling(action='start') tool builds: both call the single
``_grill_text`` builder in server.py (via ``_grill_prompt_for_suggestion``), so
there is one source of truth for the text. Keyed by suggestion id, it resolves
through the model's ``_find_suggestion`` (which raises KeyError for an unknown
suggestion/map — never creating anything).

The archmap_grilling tool stays the fallback for tools-only hosts.
``register(mcp)`` is called once from server.py after `mcp` and the tools exist.
"""
from __future__ import annotations

from fastmcp.exceptions import PromptError

from . import server as srv


def register(mcp) -> None:
    """Register the grill_candidate prompt on `mcp`. Called once from server.py
    after `mcp` and the grilling tool/builder are defined."""

    @mcp.prompt
    def grill_candidate(map: str, suggestion_id: str) -> str:
        """Enter the /deepen grilling loop for a flagged deepening candidate.

        Renders the SAME walkthrough text the archmap_grilling(action='start')
        tool produces, so a user can kick off a grilling from a prompt picker.

        Args:
            map: the map id the candidate lives in.
            suggestion_id: the candidate id (from a flag ack / the module record).
        """
        try:
            return srv._grill_prompt_for_suggestion(
                srv.REGISTRY.store(map), map, suggestion_id)
        except (KeyError, ValueError) as e:
            raise PromptError(str(e).strip("'\"")) from e
