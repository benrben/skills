"""Shared YAML serialization — the one helper BOTH the MCP tools (server.py) and
the archmap:// resources (resources.py) build their text output on.

Extracted here so the tool-output path and the resource-read path share ONE
serializer with no circular import: server.py imports this, resources.py imports
this, and neither imports the other just to reach `_yaml`.

WHY YAML (token economy): YAML drops JSON's braces/quotes/commas and leans on
indentation for nesting, so the same payload costs markedly fewer tokens when it
lands in the model's context. Both surfaces want that: a resource read returns
YAML text, and (per the tool-yaml pass) every MCP TOOL result is now serialized to
YAML text too — one text block, NO JSON structuredContent — via the generic
output hook in server.py that calls back into this helper.
"""
from __future__ import annotations

import yaml


def _yaml(obj) -> str:
    """Serialize a payload to YAML — the generic helper every structured surface
    builds on. Block style (not flow) + insertion order preserved + unicode kept raw,
    so the output reads as indented key: value lines with no JSON syntax overhead."""
    return yaml.safe_dump(obj, default_flow_style=False, sort_keys=False,
                          allow_unicode=True)
