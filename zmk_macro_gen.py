#!/usr/bin/env python3
"""
Turn typed text into ZMK macro bindings.

Reads text from stdin until EOF (Ctrl-D), converts each character into the
matching ZMK key press, and prints a ready-to-paste ZMK_MACRO block.

Examples
--------
    $ ./zmk_macro_gen.py --name m_sig_cumps
    Cumps,
    Heiko
    ^D
    // Cumps, / Heiko
    ZMK_MACRO(m_sig_cumps,
            wait-ms = <MACRO_WAIT>;
            tap-ms = <MACRO_TAP>;
            bindings = <&kp C &kp U &kp M &kp P &kp S &kp COMMA &kp RET
                &kp LS(H) &kp E &kp I &kp K &kp O>;
            )

    $ echo -n "Agenda:" | ./zmk_macro_gen.py --name m_ag --bindings-only
    &kp A &kp G &kp E &kp N &kp D &kp A &kp COLON

Characters that have no single keycode are written with {braces}:

    {RET} {SPACE} {TAB} {LS(H)} {LC(B)} {EURO}

Anything the mapper does not know is reported on stderr and skipped, so the
output never silently contains an invalid keycode.
"""

from __future__ import annotations

import argparse
import sys

# Single characters -> ZMK keycode names.
CHAR_MAP: dict[str, str] = {
    " ": "SPACE",
    "!": "EXCL",
    '"': "DQT",
    "#": "HASH",
    "$": "DLLR",
    "%": "PRCNT",
    "&": "AMPS",
    "'": "SQT",
    "(": "LPAR",
    ")": "RPAR",
    "*": "STAR",
    "+": "PLUS",
    ",": "COMMA",
    "-": "MINUS",
    ".": "DOT",
    "/": "FSLH",
    ":": "COLON",
    ";": "SEMI",
    "<": "LT",
    "=": "EQUAL",
    ">": "GT",
    "?": "QMARK",
    "@": "AT",
    "[": "LBKT",
    "\\": "BSLH",
    "]": "RBKT",
    "^": "CARET",
    "_": "UNDER",
    "`": "GRAVE",
    "{": "LBRC",
    "|": "PIPE",
    "}": "RBRC",
    "~": "TILDE",
}

# Sequences that start with a brace and are written explicitly by the user.
BRACE_MAP: dict[str, str] = {
    "RET": "RET",
    "ENTER": "RET",
    "SPACE": "SPACE",
    "TAB": "TAB",
    "ESC": "ESC",
    "BSPC": "BSPC",
    "DEL": "DEL",
}

INDENT = "        "


def char_to_keycode(ch: str) -> str | None:
    """Map a single character to a ZMK keycode, or None if unknown."""
    if ch.isascii() and ch.isalpha():
        # Letters: uppercase is the shifted form of the lowercase keycode.
        return f"LS({ch.upper()})" if ch.isupper() else ch.upper()
    if ch.isdigit():
        return f"N{ch}"
    if ch == "\n":
        return "RET"
    if ch == "\t":
        return "TAB"
    return CHAR_MAP.get(ch)


def parse(text: str) -> tuple[list[str], list[str]]:
    """Return (keycodes, warnings) for the given text."""
    keycodes: list[str] = []
    warnings: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "{":
            end = text.find("}", i)
            if end == -1:
                warnings.append("unterminated '{' - rest of input ignored")
                break
            token = text[i + 1 : end]
            if token.upper() in BRACE_MAP:
                keycodes.append(BRACE_MAP[token.upper()])
            elif token:
                # Pass through anything else verbatim, e.g. LS(H) or LC(B).
                keycodes.append(token)
            else:
                warnings.append("empty '{}' ignored")
            i = end + 1
            continue
        if ch == "}":
            warnings.append("stray '}' ignored")
            i += 1
            continue
        kc = char_to_keycode(ch)
        if kc is None:
            warnings.append(f"no keycode for {ch!r} - skipped")
        else:
            keycodes.append(kc)
        i += 1
    return keycodes, warnings


def format_bindings(keycodes: list[str], per_line: int = 8) -> str:
    """Format keycodes as a `<&kp ...>` binding list, wrapped for readability."""
    if not keycodes:
        return "bindings = <>;"
    chunks = [keycodes[i : i + per_line] for i in range(0, len(keycodes), per_line)]
    first = f"{INDENT}bindings = <"
    cont = " " * len(first)
    lines = []
    for idx, chunk in enumerate(chunks):
        seg = " ".join(f"&kp {k}" for k in chunk)
        lines.append((first if idx == 0 else cont) + seg)
    lines[-1] += ">;"
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", help="macro label, e.g. m_sig_cumps")
    ap.add_argument(
        "--bindings-only",
        action="store_true",
        help="print only the <&kp ...> list, not a full ZMK_MACRO block",
    )
    ap.add_argument(
        "--per-line",
        type=int,
        default=8,
        help="keycodes per output line (default 8)",
    )
    ap.add_argument(
        "--wait-ms",
        default="MACRO_WAIT",
        help="value for wait-ms (default MACRO_WAIT)",
    )
    ap.add_argument(
        "--tap-ms",
        default="MACRO_TAP",
        help="value for tap-ms (default MACRO_TAP)",
    )
    args = ap.parse_args()

    text = sys.stdin.read()
    keycodes, warnings = parse(text)

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if not keycodes:
        print("error: no keycodes produced", file=sys.stderr)
        return 1

    if args.bindings_only:
        print(format_bindings(keycodes, args.per_line))
        return 0

    if not args.name:
        print("error: --name is required unless --bindings-only is given", file=sys.stderr)
        return 1

    # Comment showing the source text, one line per input line.
    preview = " / ".join(line for line in text.splitlines() if line.strip())
    print(f"{INDENT}// {preview}")
    print(f"{INDENT}ZMK_MACRO({args.name},")
    print(f"{INDENT}        wait-ms = <{args.wait_ms}>;")
    print(f"{INDENT}        tap-ms = <{args.tap_ms}>;")
    print(format_bindings(keycodes, args.per_line))
    print(f"{INDENT}        )")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
