#!/usr/bin/env python3
"""
Generate config/include/layers.dtsi from config/tempest.keymap.

Why tempest and not config/keymap?
----------------------------------
config/keymap is the 42-slot master: every layer carries 6 `DK` padding tokens
(corne's phantom 6th column) and `RKL`/`RKR` placeholders. tempest.keymap is
what generate_keymaps.sh already produces for a 36-key board - the padding is
gone, RKL/RKR are resolved, and it is verified correct (the equivalence harness
records tempest at 36 keys for all 12 layers).

So tempest.keymap is the authoritative 36-key expression of the layout, and we
lift the layer bodies from it verbatim, changing only the node wrapper into
ZMK_LAYER(...).

Layer ORDER is load-bearing: keymap-drawer resolves a combo's `layers` property
positionally, and combos.dtsi uses bare indices. The order below must equal the
index order used there (QWERTY=0 ... ACCENT=11).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "config" / "tempest.keymap"
OUT = REPO / "config" / "include" / "layers.dtsi"

LAYER_ORDER = [
    "QWERTY", "NUMNAV", "SYMBOL", "FUNADJ", "MOUSE", "MEDIA",
    "WMCFG", "MSOUTL", "MACROS", "BLUETH", "LOCK", "ACCENT",
]

# Behaviour arity: how many following tokens belong to this binding.
# Everything not listed is treated as arity 1 (&kp X, &trans, &none, &m_foo).
ARITY = {
    # arity 0 - take no arguments (must be listed, or they swallow the next token)
    "&leader1": 0,
    "&leader2": 0,
    "&key_repeat": 0,
    "&unstick": 0,
    "&capsw": 0,
    "&bootloader": 0,
    "&sys_reset": 0,
    "&studio_unlock": 0,
    "&none": 0,
    "&trans": 0,
    # arity 1
    "&mo": 1,
    "&sl": 1,
    "&sk": 1,
    "&tog": 1,
    "&to": 1,
    "&out": 1,
    "&mkp": 1,
    "&mmv": 1,
    "&msc": 1,
    # arity 2
    "&lt": 2,
    "&mt": 2,
    "&hm": 2,
    "&hms": 2,
    "&urm": 2,
    "&skm": 2,
    "&trm": 2,
    "&mm": 2,
}


def split_bindings(line: str) -> list[str]:
    """Split a bindings line into whole binding expressions.

    Bindings are whitespace-separated, but a binding may consume several
    tokens (`&skm MOUSE SPACE`), so we walk the line using ARITY.
    """
    toks = line.split()
    out: list[str] = []
    i = 0
    while i < len(toks):
        tok = toks[i]
        if not tok.startswith("&"):
            out.append(tok)
            i += 1
            continue
        n = ARITY.get(tok, 1)
        out.append(" ".join(toks[i : i + 1 + n]))
        i += 1 + n
    return out


def split_thumbs(thumb_line: str, layer: str) -> tuple[str, str]:
    """Return (36-key thumb row, 34-key thumb row).

    The 36-key row is    LH2 LH1 LH0 | RH0 RH1 RH2
    The 34-key row keeps LH1 LH0 | RH0 RH1 - i.e. the two INNER keys of each
    hand, dropping only the outermost pair. (In both headers LH0/RH0 are the
    innermost thumb and LH2/RH2 the outermost.)
    """
    parts = split_bindings(thumb_line)
    if len(parts) != 6:
        sys.exit(
            f"error: {layer}: thumb row has {len(parts)} bindings, expected 6 "
            f"(LH2 LH1 LH0 RH0 RH1 RH2): {parts}"
        )
    lh2, lh1, lh0, rh0, rh1, rh2 = parts
    six = f"{lh2} {lh1} {lh0} {rh0} {rh1} {rh2}"
    four = f"{lh1} {lh0} {rh0} {rh1}"
    return six, four


def main() -> int:
    src = SOURCE.read_text()

    found: dict[str, str] = {}
    for m in re.finditer(
        r'(\w+) \{\s*\n\s*display-name = "(\w+)";(.*?)bindings = <(.*?)>;',
        src,
        re.S,
    ):
        _, disp, middle, bindings = m.groups()
        # keep any inline comments that sit above the bindings (they document
        # the physical row layout and are worth preserving)
        comments = [
            line.rstrip()
            for line in middle.split("\n")
            if line.strip().startswith("//")
        ]
        found[disp] = (bindings.strip("\n"), comments)

    missing = [n for n in LAYER_ORDER if n not in found]
    if missing:
        sys.exit(f"error: layers missing from {SOURCE.name}: {missing}")

    out: list[str] = [
        "// Layer definitions, written with zmk-helpers ZMK_LAYER.\n",
        "//\n",
        "// Included by every keyboard keymap after its own key-labels header,\n",
        "// so the same source serves 36-key boards (36.h) and the 34-key sweep\n",
        "// (34.h) - the label names resolve to each board's own numbering.\n",
        "//\n",
        "// ORDER MATTERS: this order defines the numeric layer indices used by\n",
        "// the `layers` argument of ZMK_COMBO in combos.dtsi.\n",
        "//\n",
        "// THUMB ROWS\n",
        "// ----------\n",
        "// Every layer's last line is its six thumb keys:\n",
        "//\n",
        "//     LH2 LH1 LH0 | RH0 RH1 RH2     (36-key boards)\n",
        "//\n",
        "// Sweep has only four (LH1 LH0 | RH0 RH1), so the outermost pair is\n",
        "// dropped there and the two inner keys of each hand keep their binding.\n",
        "// zmk-helpers offers no macro for this - it only provides the per-board\n",
        "// THUMBS_L/THUMBS_R label lists, which serve hold-trigger positions, not\n",
        "// layer bodies. The divergence is therefore explicit below.\n\n",
    ]

    for name in LAYER_ORDER:
        bindings, comments = found[name]
        body_lines = [ln.rstrip() for ln in bindings.split("\n") if ln.strip()]
        thumb_line = body_lines[-1]
        main_lines = body_lines[:-1]

        out.append(f'ZMK_LAYER_NAMED({name.lower()}, "{name}",\n')
        for ln in comments:
            out.append(f"    {ln}\n")
        for ln in main_lines:
            out.append(f"    {ln.strip()}\n")

        six, four = split_thumbs(thumb_line, name)
        if six == four:
            out.append(f"    {six}\n")
        else:
            out.append("#ifdef ZMK_KB_34\n")
            out.append(f"    {four}\n")
            out.append("#else\n")
            out.append(f"    {six}\n")
            out.append("#endif\n")
        out.append(")\n\n")

    OUT.write_text("".join(out))
    print(f"wrote {OUT} ({len(LAYER_ORDER)} layers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
