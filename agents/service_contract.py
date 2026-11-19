"""Summarize function boundaries directly from buggy production source."""

import ast
from typing import Callable

from agents.source_context import SourceWindow

_FUNCTION = (ast.FunctionDef, ast.AsyncFunctionDef)


def _behavior(function) -> list[str]:
    pending = list(reversed(function.body))
    effects = []
    while pending and len(effects) < 4:
        node = pending.pop()
        if isinstance(node, (*_FUNCTION, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Return):
            effects.append("return " + (ast.unparse(node.value) if node.value else "None"))
        elif isinstance(node, ast.Raise):
            effects.append("raise " + (ast.unparse(node.exc) if node.exc else "(re-raise)"))
        else:
            pending.extend(reversed(list(ast.iter_child_nodes(node))))
    return [effect[:160] for effect in dict.fromkeys(effects)]


def source_contracts(windows: list[SourceWindow], read: Callable[[str], str | None]) -> str:
    summaries = []
    seen = set()
    parsed = {}
    for window in windows:
        if window.path not in parsed:
            try:
                tree = ast.parse(read(window.path) or "")
            except (SyntaxError, ValueError, RecursionError):
                parsed[window.path] = []
            else:
                parsed[window.path] = [node for node in ast.walk(tree) if isinstance(node, _FUNCTION)]
        overlapping = [
            node for node in parsed[window.path]
            if node.lineno <= window.last and node.end_lineno >= window.first
        ]
        center = window.anchor
        overlapping.sort(key=lambda node: (
            not node.lineno <= center <= node.end_lineno,
            max(node.lineno - center, center - node.end_lineno, 0),
            node.end_lineno - node.lineno,
        ))
        if not overlapping:
            continue
        function = overlapping[0]
        key = (window.path, function.lineno)
        if key in seen:
            continue
        seen.add(key)
        signature = f"{function.name}({ast.unparse(function.args)})"
        if function.returns:
            signature += f" -> {ast.unparse(function.returns)}"
        effects = _behavior(function)
        summaries.append("\n".join([
            f"{window.path}:{function.lineno}  {signature[:240]}",
            *(f"  {effect}" for effect in effects),
        ]))
    return "\n\n".join(summaries)
