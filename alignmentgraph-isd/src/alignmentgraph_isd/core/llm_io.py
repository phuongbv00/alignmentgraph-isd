"""Talking to a chat model and getting usable JSON back.

Pure functions — no agent, no graph, no config: a small model returns broken
JSON often enough that parsing it is a first-class concern, not a detail of
whoever called.

What each one answers is a MEASURED failure, not a hypothetical:
``_fix_json_control_chars`` and ``_close_unbalanced_json`` a truncated
completion, and ``_is_truncation_error`` the retry that must go out UNBOUND or
it truncates again at the same place.
"""
from __future__ import annotations

import json
import re
import warnings


def _is_truncation_error(exc: Exception) -> bool:
    """A JSON-mode response cut off at the model's max output length raises
    (rather than returning partial text). Detect that so the caller can retry
    unbound and salvage what was produced."""
    msg = str(exc).lower()
    return (
        "length limit" in msg
        or "max_tokens" in msg
        or ("finish_reason" in msg and "length" in msg)
        or ("could not parse" in msg and "length" in msg)
    )


#: Provider names for "the generation hit the token cap". OpenAI-compatible
#: backends say ``length``; Anthropic says ``max_tokens``.
_TRUNCATED_REASONS = frozenset({"length", "max_tokens", "MAX_TOKENS"})


def finish_reason(result) -> str:
    """Why the model stopped, or "" if the backend does not say.

    Read because a NATIVE tool call that ran out of tokens comes back as a
    well-formed call with missing or partial arguments — there is no parse
    error to catch. Without this the loop cannot tell "the model sent an empty
    submit" from "the submit was cut off mid-arguments", and it charges the
    model for the second.
    """
    meta = getattr(result, "response_metadata", None) or {}
    if not isinstance(meta, dict):
        return ""
    for key in ("finish_reason", "stop_reason"):
        value = meta.get(key)
        if value:
            return str(value)
    return ""


def was_truncated(result) -> bool:
    return finish_reason(result) in _TRUNCATED_REASONS


def _extract_token_usage(result) -> tuple[int, int]:
    """(prompt_tokens, completion_tokens) from a LangChain chat result, robust
    across the two shapes providers actually use:

    - ``usage_metadata`` — a **dict** ``{"input_tokens", "output_tokens", ...}``
      (LangChain's normalized form — read it as a dict, never with ``getattr``,
      which silently returns 0).
    - ``response_metadata["token_usage"]`` — the raw provider block, OpenAI-style
      ``{"prompt_tokens", "completion_tokens"}`` (dict or object).
    """
    def _get(obj, key, default=0):
        if obj is None:
            return default
        if isinstance(obj, dict):
            value = obj.get(key, default)
        else:
            value = getattr(obj, key, default)
        return value if isinstance(value, int) else default

    usage = getattr(result, "usage_metadata", None)
    if usage:
        prompt = _get(usage, "input_tokens")
        completion = _get(usage, "output_tokens")
        if prompt or completion:
            return prompt, completion

    response_metadata = getattr(result, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") if isinstance(response_metadata, dict) else None
    if token_usage:
        return _get(token_usage, "prompt_tokens"), _get(token_usage, "completion_tokens")
    return 0, 0


def _fix_json_control_chars(s: str) -> str:
    """Fix literal control characters (newline, tab, etc.) inside JSON string values.

    Only modifies characters that appear inside quoted strings.
    Structural whitespace outside strings is left untouched.
    """
    result = []
    in_string = False
    escape_next = False
    for ch in s:
        if escape_next:
            result.append(ch)
            escape_next = False
        elif in_string and ch == "\\":
            result.append(ch)
            escape_next = True
        elif ch == '"':
            result.append(ch)
            in_string = not in_string
        elif in_string and ch == "\n":
            result.append("\\n")
        elif in_string and ch == "\r":
            result.append("\\r")
        elif in_string and ch == "\t":
            result.append("\\t")
        else:
            result.append(ch)
    return "".join(result)


def _close_unbalanced_json(s: str) -> str:
    """Append missing closing JSON delimiters when a response stops too early."""
    stack: list[str] = []
    in_string = False
    escape_next = False

    for ch in s:
        if escape_next:
            escape_next = False
            continue
        if in_string and ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
            else:
                return s

    if in_string or not stack:
        return s
    return s + "".join(reversed(stack))


def _salvage_json(text: str) -> dict:
    """Best-effort deterministic repair of malformed LLM JSON via json-repair.

    Returns a non-empty dict on success, ``{}`` otherwise (including when the
    library is unavailable, so callers degrade to the pre-salvage behavior).
    A top-level list — e.g. the model emitted ``[...]`` then a second ``{...}``
    value — is merged dict-by-dict in order, mirroring the section-dict shape
    every specialist expects.
    """
    try:
        import json_repair
    except ImportError:
        return {}
    try:
        repaired = json_repair.loads(text)
    except Exception:
        return {}
    if isinstance(repaired, dict) and repaired:
        return repaired
    if isinstance(repaired, list):
        merged: dict = {}
        for item in repaired:
            if isinstance(item, dict):
                merged.update(item)
        if merged:
            return merged
    return {}


def parse_json_array(raw: str) -> tuple[list, int]:
    """Recover a JSON ARRAY OF OBJECTS from text that will not parse, as
    ``(items, dropped)``.

    :func:`parse_json_response` cannot do this and must not be asked to: every
    path in it returns a dict, and its "first complete object" pass decodes
    from the leading ``{``, so on a malformed array it returns element ONE and
    calls that the answer. MEASURED (a 2B submit): three assessment items whose
    array closed as ``..."]}`` instead of ``..."}]`` — the last two brackets
    transposed — came back as a single dict holding item 1. Only the type check
    in ``coerce_args`` stopped one item being committed as though it were the
    whole set.

    So this scans for top-level ``{...}`` blocks by brace balance, ignoring
    braces inside strings, and parses each independently. One malformed element
    costs that element, not the whole submission.

    ``dropped`` is how many blocks would not parse, returned rather than
    swallowed: recovering 2 of 3 items and saying nothing is the same class of
    failure as recovering 1.

    Brace balance alone is not enough, and the case it misses is an element
    short one CLOSING brace: depth never returns to 0, every element after it
    is swallowed into a block that never terminates, and the whole array is
    charged as one dropped block. MEASURED (run 2b9e911a): a rubric criterion
    closing ``"full"}]}`` instead of ``"full"}}]}`` recovered 0 of 3 items
    though element one was recoverable alone, the submit was rejected three
    times as "arrived as text", and the item the round existed to produce was
    never written.

    So a ``}`` ALSO ends an element at bracket depth 1 (only the outer array
    open) when ``,`` then ``{`` follows. That sequence can mean nothing else
    inside the outer array: within an object a comma is followed by a key, and
    within a nested ``"rubric": [{…},{…}]`` the same text sits at bracket depth
    2 — which brace depth cannot tell apart, both leaving it at 1.
    """
    text = raw.strip()
    start = text.find("[")
    if start == -1:
        return [], 0
    items: list = []
    dropped = 0
    depth = 0
    brackets = 0
    in_string = False
    escaped = False
    block_start = -1
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            brackets += 1
        elif char == "]":
            brackets -= 1
        elif char == "{":
            if depth == 0:
                block_start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if block_start != -1 and (
                    depth == 0
                    or (depth > 0 and brackets == 1
                        and _starts_next_element(text, index + 1))):
                fragment = text[block_start:index + 1]
                parsed = _loads_object(fragment)
                if parsed is None:
                    dropped += 1
                else:
                    items.append(parsed)
                block_start = -1
                depth = 0
            elif depth < 0:
                # A stray closer, which is exactly the transposition this
                # exists for. Resynchronise rather than abandon the rest.
                depth = 0
                block_start = -1
    if block_start != -1:
        # The LAST element never closed. The common shape is an array ending
        # `..."]` where `..."}]` was meant — the element's own closing brace
        # dropped — which the `, {` rule above cannot see because nothing
        # follows. Closing what is open is the same structural repair, and
        # the element's text is untouched. MEASURED (run 9efc3cfa,
        # content:MU-C-01): a one-material array closed that way was rejected
        # four times as "arrived as text", the set gave up and was regenerated.
        tail = text[block_start:].rstrip()
        while tail.endswith("]"):
            tail = tail[:-1].rstrip()
        parsed = _loads_object(tail + "}" * max(depth, 1)) if not in_string else None
        if parsed is None:
            dropped += 1
        else:
            items.append(parsed)
    return items, dropped


def close_unclosed_arrays(text: str) -> str:
    """Insert the ``]`` an array lost before the object's NEXT KEY.

    MEASURED (run 1c0a4e81, ``operator_manual``): ``"operation_procedures":
    ["1) …", "support_procedures": ["…"], …`` — the first array never closes,
    so everything after it reads as more of that array, strict parsing fails
    at the first ``:``, and the tolerant parser keeps only the fields before
    the break. Three submits lost two of four required fields that way, the
    artifact spent its budget and shipped empty.

    A string followed by ``:`` is an object KEY. Inside an array of strings
    that can mean only one thing — the array was meant to end before it — so
    the ``]`` goes in front of that key's comma. Nothing else is touched: no
    value is rewritten, and text this does not apply to comes back unchanged.

    The comma and the array must belong to the SAME container, which is why
    every opener carries its own. Read off the latest comma anywhere, the
    insertion lands outside the array it is closing: MEASURED, ``{"x": 1,
    "fm": ["fm": ["a"], …`` became ``{"x": 1], "fm": …`` — a repair that
    corrupts a part of the text that was never broken. And a key that is the
    array's FIRST token has no comma to go in front of at all, so the ``]``
    goes straight after the ``[``, leaving the empty array and the key as
    siblings; the key repeated is then the one that stands, which is exactly
    what a model naming the field twice meant. MEASURED (run d7722e8e,
    ``assessment_plan``): ``"formative_methods": ["formative_methods": ["exit
    tickets"], "lo_coverage_targets": {…}`` recovered ONE of the artifact's
    fields, so the submit was refused for a `lo_coverage_targets` the model
    could see it had just written, three times, and the stage ended.
    """
    out: list[str] = []
    # One frame per open container: its opener, where its contents begin in
    # `out`, and the latest comma seen INSIDE it (-1 = none yet).
    stack: list[list] = []
    index, length = 0, len(text)
    while index < length:
        char = text[index]
        if char == '"':
            end = index + 1
            while end < length and text[end] != '"':
                end += 2 if text[end] == "\\" else 1
            token = text[index:end + 1]
            after = end + 1
            while after < length and text[after] in " \t\r\n":
                after += 1
            if stack and stack[-1][0] == "[" and after < length and text[after] == ":":
                _, floor, comma = stack.pop()
                # In front of the comma the array already has; where it has
                # none, straight after the `[`, and then the separator the
                # key needs to stand as the next field of the object.
                out.insert(comma, "]") if comma != -1 else out.insert(floor, "],")
            out.append(token)
            index = end + 1
            continue
        if char in "[{":
            out.append(char)
            stack.append([char, len(out), -1])
            index += 1
            continue
        if char in "]}":
            if not stack:
                index += 1
                continue                # a closer with nothing open: dropped
            # The closer that MATCHES what is open — `..."]` ending an object
            # is the same slip as the one above, seen from the other end.
            char = "]" if stack.pop()[0] == "[" else "}"
        elif char == "," and stack:
            stack[-1][2] = len(out)
        out.append(char)
        index += 1
    # Whatever is still open is closed, innermost first.
    out.extend("]" if frame[0] == "[" else "}" for frame in reversed(stack))
    return "".join(out)


def _starts_next_element(text: str, index: int) -> bool:
    """Is the text from ``index`` the ``, {`` that opens the next array element?

    Whitespace-tolerant and nothing more. It is asked only at bracket depth 1,
    where ``}`` ``,`` ``{`` has exactly one meaning."""
    rest = text[index:].lstrip()
    return rest.startswith(",") and rest[1:].lstrip().startswith("{")


def _loads_object(fragment: str) -> dict | None:
    """One array element, strictly then leniently. ``None`` if neither works."""
    try:
        value = json.loads(fragment)
    except (TypeError, ValueError):
        value = parse_json_response(fragment, warn=False)
    return value if isinstance(value, dict) and value else None


def parse_json_response(raw: str, *, warn: bool = True, salvage: bool = True) -> dict:
    """Robustly parse a JSON dict from an LLM response.

    Handles: markdown fences, leading/trailing prose, literal control
    characters inside string values, and other common LLM JSON issues.
    Logs a warning (does not raise) if all attempts fail.

    ``salvage=True`` adds a final deterministic repair pass (json-repair) that
    recovers output no targeted fix above could: invalid escapes, stray quotes,
    multiple top-level values, and cap-truncated responses (keeps the complete
    prefix). ``salvage=False`` keeps the strict behavior — used by
    ``tools.coerce_args`` at the transport boundary, where a lossy parse of a
    submit argument would commit a truncated artifact as whole.
    """
    if not raw:
        return {}

    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?[ \t]*\n?", "", raw)
    cleaned = re.sub(r"\n?```[ \t]*$", "", cleaned, flags=re.MULTILINE).strip()

    last_err: json.JSONDecodeError | None = None

    # Try 1: direct parse (clean JSON)
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError as e:
        last_err = e

    # Try 1b: decode the first complete JSON object and ignore trailing garbage
    # ("Extra data" — the model emitted valid JSON then kept talking, or closed
    # the root object early). Also skips any leading prose before the first '{'.
    brace = cleaned.find("{")
    if brace != -1:
        try:
            obj, _end = json.JSONDecoder().raw_decode(cleaned[brace:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError as e:
            last_err = e

    # Try 2: the outermost {} block, with targeted fixes. (Plain json.loads
    # of it cannot succeed where Try 1b's raw_decode from the same brace
    # failed, so that attempt is not repeated.)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        candidate = match.group(0)

        # Try 3: fix literal control chars inside string values (stateful)
        try:
            result = json.loads(_fix_json_control_chars(candidate))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError as e:
            last_err = e

        # Try 4: remove trailing commas (another common LLM issue)
        try:
            no_trailing = re.sub(r",(\s*[}\]])", r"\1", candidate)
            result = json.loads(_fix_json_control_chars(no_trailing))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError as e:
            last_err = e

        # Try 5: deterministic salvage via json-repair. Only reached when every
        # targeted fix above failed, so well-formed responses never take this
        # path. Covers the malformed-JSON classes small models (0.8B) emit:
        # invalid escapes (\'), stray quotes after brackets, several top-level
        # values, and mid-string truncation at the completion cap. Runs BEFORE
        # the bracket-closing fallback because json-repair keeps the complete
        # truncated prefix (it closes the string mid-value), whereas closing
        # the regex candidate cuts at the last '}' and drops everything after.
        if salvage:
            salvaged = _salvage_json(cleaned) or _salvage_json(candidate)
            if salvaged:
                return salvaged

        # Try 6: append missing closing braces/brackets for truncated JSON.
        try:
            balanced = _close_unbalanced_json(no_trailing)
            result = json.loads(_fix_json_control_chars(balanced))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError as e:
            last_err = e

    elif salvage:
        # No '{' block found at all (e.g. a bare top-level array): still give
        # json-repair a chance before giving up.
        salvaged = _salvage_json(cleaned)
        if salvaged:
            return salvaged

    if not warn:
        return {}

    err_ctx = ""
    if last_err is not None:
        pos = last_err.pos
        snip = cleaned[max(0, pos - 40):pos + 40] if cleaned else ""
        err_ctx = f" | Error at pos {pos}: {last_err.msg!r} near {snip!r}"
    warnings.warn(
        f"parse_json_response: all attempts failed (response len={len(raw)})"
        f"{err_ctx}"
    )
    return {}
