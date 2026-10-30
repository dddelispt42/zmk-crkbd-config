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
        "// the `layers` argument of ZMK_COMBO in combos.dtsi.\n\n",
    ]

    for name in LAYER_ORDER:
        bindings, comments = found[name]
        # re-indent the binding block to sit under ZMK_LAYER_NAMED(...)
        body_lines = [ln.rstrip() for ln in bindings.split("\n") if ln.strip()]
        # node name is lowercased so it cannot collide with the layer-index
        # #defines; the display name is preserved verbatim.
        out.append(f'ZMK_LAYER_NAMED({name.lower()}, "{name}",\n')
        for ln in comments:
            out.append(f"    {ln}\n")
        for ln in body_lines:
            out.append(f"    {ln.strip()}\n")
        out.append(")\n\n")

    OUT.write_text("".join(out))
    print(f"wrote {OUT} ({len(LAYER_ORDER)} layers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
