#!/usr/bin/env python3
"""
One-shot extractor: split config/keymap (the single-source master) into the
shared zmk-helpers include files.

This exists so the refactor is *mechanical and reviewable* rather than
hand-transcribed from 935 lines. It is a migration tool: once the new structure
is in place and verified, both this script and config/keymap are deleted.

Extraction rules
----------------
The master file has this structure:

    lines   1- 21  header: #include <...>, pointing values
    lines  23- 26  KEYS_L / KEYS_R / THUMBS   (-> keys.h, superseded by 36.h)
    lines  28- 39  layer index #defines       (DROPPED: collide with ZMK_LAYER)
    lines  41- 50  combo timing #defines      (-> keys.h)
    lines  51- 62  URML/HRML/... behaviour macros (-> behaviors.dtsi)
    lines  64- 87  MU1/MH1/... + TEXT() machinery (-> macros.dtsi)
    line   90- 92  &sl override               (-> behaviors.dtsi)
    line   94       / {  root node
    lines 111-300  combos                    (-> combos.dtsi, RELABELLED)
    lines 302-619  macros                    (-> macros.dtsi)
    lines 621-741  behaviors                 (-> behaviors.dtsi)
    lines 744-935  keymap                    (-> layers.dtsi, converted)

Combos are the only part that is *transformed* rather than moved: their
numeric key-positions are rewritten to key labels and their layer references
to bare indices. Everything else is copied verbatim so a reviewer can diff.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MASTER = REPO / "config" / "keymap"
OUT = REPO / "config" / "include"

# Layer order in the master file == numeric layer index.
LAYERS = [
    "QWERTY", "NUMNAV", "SYMBOL", "FUNADJ", "MOUSE", "MEDIA",
    "WMCFG", "MSOUTL", "MACROS", "BLUETH", "LOCK", "ACCENT",
]
LAYER_INDEX = {name: i for i, name in enumerate(LAYERS)}

# Displays the combos' numeric positions in terms of zmk-helpers labels.
LABELS = Path(REPO / "config" / "zmk-helpers-repo" / "include" / "zmk-helpers"
              / "key-labels" / "36.h")


def load_labels() -> dict[int, str]:
    txt = LABELS.read_text()
    return {int(v): n for n, v in
            re.findall(r"#define (L[TRMBH]\d|R[TRMBH]\d)\s+(\d+)", txt)}


def slice_lines(src: list[str], start: int, end: int) -> str:
    """1-based inclusive start, exclusive end."""
    return "\n".join(src[start - 1:end - 1]) + "\n"


def find(src: str, pat: str) -> int:
    m = re.search(pat, src, re.M)
    if not m:
        sys.exit(f"error: pattern not found: {pat!r}")
    return src[: m.start()].count("\n") + 1


def main() -> int:
    raw = MASTER.read_text()
    src = raw.split("\n")
    labels = load_labels()

    # --- locate the combos / macros / behaviors blocks -------------------
    combos_start = find(raw, r"\n    combos \{")
    combos_end = find(raw, r"\n    macros \{")
    macros_start = combos_end
    macros_end = find(raw, r"\n    behaviors \{")
    behaviors_start = macros_end
    behavior_leader = find(raw, r"^\s+leader1: leader1 \{")
    keymap_start = find(raw, r"\n        keymap \{")

    # behaviors block ends where the keymap node begins; the `};` that closes
    # the `behaviors {` node sits just before it.
    behaviors_end = find(raw, r"\n        keymap \{")

    # --- 1. combos.dtsi: relabel positions, numeric layer refs ----------
    combo_block = slice_lines(src, combos_start, combos_end)
    # drop the `combos {` wrapper - ZMK_COMBO emits its own node
    combo_body = combo_block
    combo_body = re.sub(r"^\s*combos \{\s*\n", "", combo_body)
    combo_body = re.sub(r"\n\s*\};\s*$", "\n", combo_body)

    def relabel(match: re.Match) -> str:
        # only rewrite the line that is NOT commented as another keyboard
        nums = [int(x) for x in match.group(1).split()]
        unknown = [n for n in nums if n not in labels]
        if unknown:
            sys.exit(f"error: positions {unknown} have no 36.h label")
        return " ".join(labels[n] for n in nums)

    out_combos: list[str] = []
    out_combos.append("// Combos, written in zmk-helpers key labels.\n")
    out_combos.append("//\n")
    out_combos.append("// Positions are board-independent: LT4/LM0/LH1 resolve to\n")
    out_combos.append("// whatever integer each keyboard's key-labels header assigns,\n")
    out_combos.append("// so one definition serves corne/tempest/seppelit/sweep.\n")
    out_combos.append("// Layer references are bare indices matching the order of the\n")
    out_combos.append("// ZMK_LAYER definitions in layers.dtsi.\n\n")

    for m in re.finditer(r"combo_(\w+) \{(.*?)\n        \};", combo_body, re.S):
        name, body = m.group(1), m.group(2)
        # Each combo carries one key-positions line per keyboard, annotated
        # ONLY-FOR-CORNE / -TEMPEST / -SWEEP. We take the TEMPEST line: it is
        # already numbered in the canonical 36-key space that zmk-helpers'
        # 36.h describes, which is exactly the space the labels express.
        # (Corne's line uses the legacy 42-key numbering with its DK padding,
        # and sweep's is byte-identical to tempest's - see FINDINGS.md.)
        pos_matches = re.findall(r"key-positions = <([^>]+)>;(.*)", body)
        if not pos_matches:
            sys.exit(f"error: combo {name} has no key-positions")
        chosen = None
        for nums, comment in pos_matches:
            if "TEMPEST" in comment:
                chosen = nums
                break
        if chosen is None:
            # no annotation: single-keyboard combo, use the only line
            chosen = pos_matches[0][0]
        lay = re.search(r"layers = <([^>]+)>;", body)
        to = re.search(r"timeout-ms = <([^>]+)>;", body)
        idle = re.search(r"require-prior-idle-ms = <([^>]+)>;", body)
        bind = re.search(r"bindings = <([^>]+)>;", body)
        if not (lay and to and idle and bind):
            sys.exit(f"error: combo {name} missing attributes")
        # `chosen` is already the canonical 36-key numbering
        nums = [int(x) for x in chosen.split()]
        unknown = [n for n in nums if n not in labels]
        if unknown:
            sys.exit(f"error: {name}: positions {unknown} have no 36.h label")
        label_pos = " ".join(labels[n] for n in nums)
        layer_idx = []
        for lname in lay.group(1).split():
            if lname not in LAYER_INDEX:
                sys.exit(f"error: {name}: unknown layer {lname}")
            layer_idx.append(str(LAYER_INDEX[lname]))
        out_combos.append(
            f"ZMK_COMBO({name}, {bind.group(1)}, {label_pos}, "
            f"{' '.join(layer_idx)}, {to.group(1)}, {idle.group(1)})\n"
        )

    # --- 2. macros.dtsi: all ZMK_MACRO definitions ---------------------
    # NOTE: the TEXT()/NARG/KPnn helper machinery that earlier revisions of
    # config/keymap carried is gone - the signature macros now spell out
    # explicit &kp lists. We therefore copy just the MU*/MH*/ML* convenience
    # macros and the ZMK_MACRO block.
    hdr_mu_start = find(raw, r"^// define AHK macro keys")
    hdr_mu_end = find(raw, r"^// more macros to shorten the definitions")
    text_machinery = slice_lines(src, hdr_mu_start, hdr_mu_end)

    macro_block = slice_lines(src, macros_start, macros_end)
    macro_body = re.sub(r"^\s*macros \{\s*\n", "", macro_block)
    macro_body = re.sub(r"\n\s*\};\s*$", "\n", macro_body)

    # --- 3. behaviors.dtsi: macros + &sl + behaviors block --------------
    urml_start = find(raw, r"^// Upper row mods macro")
    urml_end = find(raw, r"^// define AHK macro keys")
    urml_block = slice_lines(src, urml_start, urml_end)

    sl_start = find(raw, r"^&sl \{")
    sl_end = find(raw, r"^/\s*\{")
    sl_block = slice_lines(src, sl_start, sl_end)

    beh_body = re.sub(r"^\s*behaviors \{\s*\n", "", slice_lines(src, behaviors_start, behaviors_end))
    beh_body = re.sub(r"\n\s*\};\s*\n?\s*$", "\n", beh_body)
    # ZMK_HOLD_TAP-style conversion is NOT applied blindly: the blocks are
    # already valid devicetree and keeping them verbatim keeps the diff honest.

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "combos.dtsi").write_text("".join(out_combos))
    (OUT / "macros.dtsi").write_text(
        "// Macros.\n\n" + text_machinery + "\n/ {\n    macros {\n"
        + macro_body + "    };\n};\n"
    )
    (OUT / "behaviors.dtsi").write_text(
        "// Custom behaviours, hold-taps and the sticky-layer override.\n\n"
        + urml_block + sl_block + "\n/ {\n    behaviors {\n"
        + beh_body + "    };\n};\n"
    )
    print("wrote combos.dtsi, macros.dtsi, behaviors.dtsi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
