"""Minimal, dependency-free helpers for reading the structure of HCL files.

This is not a full HCL parser. It finds labelled blocks by brace matching,
skipping strings and comments, which is enough to answer questions such as
"which resources does this module declare" and "what does this assert block
reference". Callers treat the results as a heuristic, never as proof.
"""
import re


def strip_comments(text):
    out, i, n = [], 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif c == "#" or text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _match_brace(text, open_idx):
    depth, i, n, in_str = 0, open_idx, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced braces")


def blocks(text, kind):
    """Yield (labels, body) for every `kind "l1" "l2" {` block in text.

    Nested blocks of the same kind are found too, which is what callers want
    for things like `assert` inside `run`.
    """
    pattern = re.compile(r'(?m)^[ \t]*' + re.escape(kind) + r'((?:[ \t]+"[^"\n]*")*)[ \t]*\{')
    for m in pattern.finditer(text):
        labels = re.findall(r'"([^"\n]*)"', m.group(1))
        open_idx = m.end() - 1
        close_idx = _match_brace(text, open_idx)
        yield labels, text[open_idx + 1 : close_idx]


def attribute(body, name):
    """Return the raw expression text of a top-level `name = ...` line, or None."""
    m = re.search(r'(?m)^[ \t]*' + re.escape(name) + r'[ \t]*=[ \t]*(.+)$', body)
    return m.group(1).strip() if m else None


def bracket_list(body, name):
    """Return the raw text inside `name = [ ... ]`, spanning lines, or ''."""
    m = re.search(r'(?m)^[ \t]*' + re.escape(name) + r'[ \t]*=[ \t]*\[', body)
    if not m:
        return ""
    depth, i = 0, m.end() - 1
    while i < len(body):
        if body[i] == "[":
            depth += 1
        elif body[i] == "]":
            depth -= 1
            if depth == 0:
                return body[m.end() : i]
        i += 1
    return body[m.end() :]
