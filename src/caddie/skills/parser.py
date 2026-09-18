"""Parses an analytics skill's raw output into a markdown string and a
code string.

An analytics skill's own instructions produce markdown restating the
question plus a fenced code block (SQL or Python) meant for the
notebook's code cell. This is the one output shape Caddie core knows
about — it has no idea what's inside the code or markdown.
"""

import re
from dataclasses import dataclass

_CODE_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class SkillOutput:
    markdown: str
    code: str


def parse_skill_output(raw_output: str) -> SkillOutput:
    """Split a skill's raw text output into markdown and code.

    Raises ValueError if no fenced code block is present — a skill
    that doesn't return one hasn't produced a usable output shape.
    """
    match = _CODE_FENCE_RE.search(raw_output)
    if match is None:
        raise ValueError(
            "Skill output contains no fenced code block; expected one "
            "SQL/Python code fence plus markdown."
        )

    code = match.group(1).strip()
    markdown = (raw_output[: match.start()] + raw_output[match.end() :]).strip()
    return SkillOutput(markdown=markdown, code=code)
