from __future__ import annotations

import re
from collections import Counter

from app.agent.artifact_directives import (
    ARTIFACT_DIRECTIVE_LINE_PATTERN,
    ARTIFACT_DIRECTIVE_PATTERN,
    canonical_artifact_id,
)
from app.agent.evidence import EvidenceBundle
from app.agent.time_context import is_time_only_question

UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
NUMBER_PATTERN = re.compile(r"(?<![\w])[-+]?\d[\d,]*(?:\.\d+)?%?")
RAW_HTML_PATTERN = re.compile(r"<\s*/?\s*[A-Za-z][^>]*>")
OUTER_FENCE_PATTERN = re.compile(
    r"\A\s*```(?:markdown|md)?[ \t]*\r?\n(?P<body>.*)\r?\n```\s*\Z",
    re.IGNORECASE | re.DOTALL,
)


ATX_HEADING_PATTERN = re.compile(r"^ {0,3}(?P<marks>#{1,6})(?:[ \t]+(?P<text>.*?))?[ \t]*$")
SETEXT_H1_PATTERN = re.compile(r"^ {0,3}=+[ \t]*$")
SLASH_COMMAND_PATTERN = re.compile(r"^/[\w-]+\s*")
TITLE_LENGTH = 80


def normalize_final_answer(markdown: str) -> str:
    """Apply deterministic presentation cleanup without changing answer content."""

    stripped = markdown.strip()
    match = OUTER_FENCE_PATTERN.fullmatch(stripped)
    if match is not None:
        return match.group("body").strip()
    return stripped


def _unfenced_lines(lines: list[str]) -> list[bool]:
    """Mark which lines sit outside fenced code blocks."""
    outside: list[bool] = []
    fence: str | None = None
    for line in lines:
        stripped = line.lstrip()
        marker = next((fence for fence in ("```", "~~~") if stripped.startswith(fence)), None)
        if marker is not None:
            outside.append(False)
            fence = None if fence == marker else fence or marker
            continue
        outside.append(fence is None)
    return outside


def _heading_text(raw: str | None) -> str:
    # A closing sequence of '#' is decoration, not title text.
    return re.sub(r"(?:^|[ \t]+)#+$", "", (raw or "").strip()).strip()


def _h1_lines(lines: list[str]) -> list[tuple[int, str]]:
    outside = _unfenced_lines(lines)
    found: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if not outside[index]:
            continue
        match = ATX_HEADING_PATTERN.match(line)
        if match and len(match.group("marks")) == 1:
            found.append((index, _heading_text(match.group("text"))))
    return found


def _setext_to_atx(lines: list[str]) -> list[str]:
    outside = _unfenced_lines(lines)
    result = list(lines)
    for index in range(1, len(lines)):
        previous = lines[index - 1]
        if (
            outside[index]
            and outside[index - 1]
            and SETEXT_H1_PATTERN.match(lines[index])
            and previous.strip()
            and not ATX_HEADING_PATTERN.match(previous)
            and (index == 1 or not lines[index - 2].strip())
        ):
            result[index - 1] = f"# {previous.strip()}"
            result[index] = ""
    return result


def answer_title(markdown: str) -> str | None:
    """Return the answer's title: its first level-1 heading outside code blocks."""
    headings = [text for _, text in _h1_lines(markdown.splitlines()) if text]
    return headings[0] if headings else None


def fallback_title(question: str) -> str:
    """Build a short title from the question when the answer has none."""
    text = " ".join(question.split())
    text = SLASH_COMMAND_PATTERN.sub("", text)
    text = re.sub(r"[#*_`>\[\]]", "", text).strip(" .?!:;")
    if len(text) > TITLE_LENGTH:
        text = text[:TITLE_LENGTH].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
    return text[:1].upper() + text[1:] if text else "Analysis"


def ensure_answer_title(markdown: str, question: str) -> str:
    """Guarantee exactly one level-1 heading, placed first, so it can serve as the title.

    The first level-1 heading becomes the title. Any later level-1 headings become level-2
    sections, and content written before the title moves below it.
    """
    lines = _setext_to_atx(markdown.splitlines())
    headings = [(index, text) for index, text in _h1_lines(lines) if text]
    empty = {index for index, text in _h1_lines(lines) if not text}
    if not headings:
        title, body = fallback_title(question), [
            line for index, line in enumerate(lines) if index not in empty
        ]
    else:
        title_index, title = headings[0]
        body = []
        for index, line in enumerate(lines):
            if index == title_index or index in empty:
                continue
            if any(index == other for other, _ in headings[1:]):
                body.append(f"## {_heading_text(ATX_HEADING_PATTERN.match(line).group('text'))}")
            else:
                body.append(line)
    content = "\n".join(body).strip()
    return f"# {title}\n\n{content}" if content else f"# {title}"


def _directive_ids(markdown: str) -> tuple[list[str], list[str]]:
    ids: list[str] = []
    errors: list[str] = []
    fence: str | None = None
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        stripped = line.lstrip()
        marker = (
            "```" if stripped.startswith("```") else "~~~" if stripped.startswith("~~~") else None
        )
        if marker is not None:
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        occurrences = list(ARTIFACT_DIRECTIVE_PATTERN.finditer(line))
        if "[[artifact:" in line and not occurrences:
            errors.append(f"Malformed artifact directive on line {line_number}.")
            continue
        if not occurrences:
            continue
        if fence is not None:
            errors.append(
                f"Artifact directives are not allowed inside code fences (line {line_number})."
            )
            continue
        line_match = ARTIFACT_DIRECTIVE_LINE_PATTERN.fullmatch(line)
        if line_match is None or len(occurrences) != 1:
            errors.append(f"Artifact directive must be on its own line (line {line_number}).")
            continue
        raw = line_match.group("artifact_id")
        canonical = canonical_artifact_id(raw)
        if canonical is None:
            errors.append(f"Artifact directive on line {line_number} must use a canonical UUID.")
            continue
        ids.append(canonical)
    return ids, errors


def _normalized_number(raw: str) -> str:
    percent = raw.endswith("%")
    value = raw[:-1] if percent else raw
    value = value.replace(",", "")
    try:
        number = float(value)
    except ValueError:
        return raw
    normalized = str(int(number)) if number.is_integer() else format(number, ".15g")
    return normalized + ("%" if percent else "")


def _numbers(value: str, *, markdown: bool = False) -> set[str]:
    cleaned = UUID_PATTERN.sub(" ", value)
    cleaned = ARTIFACT_DIRECTIVE_PATTERN.sub(" ", cleaned)
    if markdown:
        cleaned = re.sub(r"(?m)^\s*\d+[.)]\s+", "", cleaned)
        cleaned = re.sub(r"(?m)^#{1,6}\s+", "", cleaned)
    return {_normalized_number(match.group(0)) for match in NUMBER_PATTERN.finditer(cleaned)}


def grounded_numbers(bundle: EvidenceBundle) -> set[str]:
    allowed = _numbers(bundle.question) | _numbers(bundle.analyst_notes)
    # Clock numbers are evidence only for a clock-only request. They must not incidentally
    # ground a business metric that happens to match a date component or UTC offset.
    if is_time_only_question(bundle.question):
        for reading in bundle.clock_results:
            allowed |= _numbers(str(reading))
        if bundle.current_time:
            allowed |= _numbers(str(bundle.current_time))
        if bundle.time_context:
            allowed |= _numbers(str(bundle.time_context.to_metadata()))
    for result in bundle.sql_results:
        allowed |= _numbers(result.sql_text)
        for row in result.rows:
            allowed |= _numbers(" ".join("" if value is None else str(value) for value in row))
    for artifact in bundle.artifacts:
        allowed |= _numbers(str(artifact.payload))
    for result in bundle.dax_results:
        allowed |= _numbers(result.dax_text)
        for row in result.rows:
            allowed |= _numbers(" ".join("" if value is None else str(value) for value in row))
    for action in bundle.management_results:
        allowed |= _numbers(str(action))
    return allowed


def validate_final_answer(
    markdown: str,
    bundle: EvidenceBundle,
    *,
    has_custom_instructions: bool = False,
) -> list[str]:
    errors: list[str] = []
    directive_ids, directive_errors = _directive_ids(markdown)
    errors.extend(directive_errors)
    counts = Counter(directive_ids)
    visible_ids = {str(item.artifact_id) for item in bundle.visible_artifacts}
    all_ids = {str(item.artifact_id) for item in bundle.artifacts}
    for artifact_id, count in counts.items():
        if count > 1:
            errors.append(f"Artifact {artifact_id} is referenced more than once.")
        if artifact_id not in visible_ids:
            qualifier = "hidden" if artifact_id in all_ids else "unknown"
            errors.append(f"Artifact {artifact_id} is {qualifier} and cannot be referenced.")
    for artifact_id in sorted(visible_ids - set(directive_ids)):
        errors.append(f"Visible artifact {artifact_id} must be referenced exactly once.")

    if RAW_HTML_PATTERN.search(markdown):
        errors.append("Raw HTML is not allowed in the final Markdown.")

    allowed_numbers = grounded_numbers(bundle)
    introduced = sorted(_numbers(markdown, markdown=True) - allowed_numbers)
    if introduced:
        errors.append(
            "The response introduces business numbers absent from verified evidence: "
            + ", ".join(introduced)
            + "."
        )
    return errors
