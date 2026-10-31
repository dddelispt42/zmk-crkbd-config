#!/usr/bin/env python3
"""
Guard against self-wrapping macros nested inside a node body.

Several zmk-helpers macros emit a COMPLETE root node rather than a fragment:

    ZMK_BEHAVIOR(name, type, ...)  ->  / { behaviors { name: name { ... }; }; };
    ZMK_COMBO_*(...)               ->  / { combos { ... }; };
    ZMK_LAYER_*(...)               ->  / { keymap { layer_... { ... }; }; };
    ZMK_UNICODE_PAIR(...)          ->  / { macros {...}; behaviors {...}; };

Calling one of these from inside an existing node body produces

    / { behaviors { ... / { behaviors { ... }; }; ... }; };

which is invalid devicetree. The compiler reports it as a parse error pointing
at the line AFTER the enclosing block closes, which is confusing enough that the
same mistake was made twice in this repo:

  * macros.dtsi wrapped ZMK_MACRO calls in an extra `macros { }`
  * behaviors.dtsi called ZMK_MOD_MORPH inside its `behaviors { }` block

`keymap parse` does NOT catch this - keymap-drawer's preprocessor is lenient -
so this check exists to catch it before CI does.

Usage:
    ./scripts/check_macro_nesting.py [config-dir]
Exit status 0 when clean, 1 when a nesting problem is found.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Macros that emit their own root node, and therefore must be called at depth 0.
SELF_WRAPPING = (
    "ZMK_BEHAVIOR",
    "ZMK_COMBO",
    "ZMK_LAYER",
    "ZMK_LAYER_NAMED",
    "ZMK_HOLD_TAP",
    "ZMK_MOD_MORPH",
    "ZMK_STICKY_KEY",
    "ZMK_CAPS_WORD",
    "ZMK_MACRO",
    "ZMK_UNICODE_PAIR",
    "ZMK_UNICODE_SINGLE",
    "ZMK_LEADER_SEQUENCE",
    "ZMK_CONDITIONAL_LAYER",
    "ZMK_APPLY_MATRIX_TRANSFORM",
)

REPO = Path(__file__).resolve().parent.parent


def strip_comments(line: str, in_block: bool) -> tuple[str, bool]:
    """Return (code-without-comments, still_in_block_comment)."""
    code = line
    if in_block:
        if "*/" not in code:
            return "", True
        code = code.split("*/", 1)[1]
        in_block = False
    while "/*" in code:
        pre, rest = code.split("/*", 1)
        if "*/" in rest:
            code = pre + rest.split("*/", 1)[1]
        else:
            return pre, True
    return code.split("//")[0], in_block


def check_file(path: Path) -> list[str]:
    problems: list[str] = []
    depth = 0
    in_block = False
    for number, raw in enumerate(path.read_text().split("\n"), 1):
        code, in_block = strip_comments(raw, in_block)
        for macro in SELF_WRAPPING:
            if f"{macro}(" in code and depth > 0:
                problems.append(
                    f"{path}:{number}: {macro}(...) called at brace depth "
                    f"{depth}; it emits its own root node and must be at "
                    f"top level"
                )
        depth += code.count("{") - code.count("}")
    if depth != 0:
        problems.append(f"{path}: unbalanced braces (final depth {depth})")
    return problems


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "config" / "include"
    files = sorted(p for p in root.rglob("*") if p.suffix in (".dtsi", ".h", ".keymap"))
    if not files:
        print(f"error: no .dtsi/.h/.keymap files under {root}", file=sys.stderr)
        return 1

    problems: list[str] = []
    for path in files:
        problems.extend(check_file(path))

    if problems:
        print(f"FAIL - {len(problems)} macro nesting problem(s):")
        for p in problems:
            print(f"  X {p}")
        print(
            "\nA macro that emits '/ { ... }' cannot be called inside another "
            "node body. Move it to the top level of the file."
        )
        return 1

    print(f"OK - {len(files)} file(s) checked, no self-wrapping macro is nested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
