#!/usr/bin/env python3
"""
Generate a keymap-drawer "virtual layer" YAML describing the leader-key
sequences, so keymap-drawer can render them (it cannot discover them itself:
leader sequences are properties of a behavior, not key bindings).

Everything is derived from config/keymap - the single source of truth. Do not
edit the generated file (config/leader.yaml) by hand; edit config/keymap and
re-run this script (generate_keymaps.sh does that automatically).

Usage:
    ./generate_leader_yaml.py [--source config/keymap] [--out config/leader.yaml]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Number of key positions per layer row in this keymap (3 rows of 10 + 6 thumbs).
ROW_SIZES = [10, 10, 10, 6]
TOTAL_POSITIONS = sum(ROW_SIZES)

# Human readable descriptions for the macros a leader sequence can bind to.
# Keys are the macro label as written in the keymap. Keep these SHORT:
# keymap-drawer truncates wide legends (shrink_wide_legends), so >~8 chars get
# an ellipsis.
MACRO_LABELS: dict[str, str] = {
    "m_sig_cumps": "Cumps",
    "m_sig_o": "Obrigado",
    "m_sig_mo": "Muito ob.",
    "m_sig_oc": "Obr.+cumps",
    "m_sig_co": "Cumps+obr",
    "m_sig_br": "Best reg",
    "m_sig_ty": "Thank you",
    "m_sig_tb": "TY+best",
    "m_sig_th": "TY Riemer",
    "m_sig_yw": "You're W.",
    "m_ag": "Agenda:",
    "m_ob": "Objective:",
    "m_ac": "Actions:",
    "m_ao": "Ag.+Obj.",
    # system sequences living in leader2
    "OUT_USB": "USB",
    "OUT_BLE": "Bluetooth",
}

# For leader2 the bindings are builtin behaviors rather than macros; give them
# readable labels too.
BINDING_LABELS: dict[str, str] = {
    "&out OUT_USB": "USB",
    "&out OUT_BLE": "BLE",
    "&bt BT_SEL 0": "BT 0",
    "&bt BT_SEL 1": "BT 1",
    "&bt BT_SEL 2": "BT 2",
    "&bt BT_CLR": "BT clear",
    "&bootloader": "Bootloader",
    "&sys_reset": "Reset",
}

LAYER_TITLES = {
    "leader1": "LEADER1",
    "leader2": "LEADER2",
}


def extract_behavior_block(src: str, label: str) -> str | None:
    """Return the text between `label: label {` and its closing `};`."""
    m = re.search(rf"^\s*{re.escape(label)}:\s*{re.escape(label)}\s*\{{", src, re.M)
    if not m:
        return None
    start = m.end()
    # find the matching closing brace of this node
    depth = 1
    i = start
    while i < len(src) and depth > 0:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
        i += 1
    return src[start : i - 1]


def parse_sequences(block: str) -> list[tuple[str, str, str]]:
    """Extract (node_name, sequence, binding) triples from a leader-key block."""
    return re.findall(
        r"(\w+)\s*\{\s*sequence = <([^>]+)>;\s*bindings = <([^>]+)>;\s*\};", block
    )


def describe(binding: str) -> str:
    """Best-effort short description for a binding."""
    binding = binding.strip()
    if binding in BINDING_LABELS:
        return BINDING_LABELS[binding]
    bare = binding.lstrip("&")
    if bare in MACRO_LABELS:
        return MACRO_LABELS[bare]
    return bare


def sequence_legend(sequence: str) -> str:
    """Turn '<C U>' into 'CU' for display."""
    return "".join(sequence.split())


def build_layer(sequences: list[tuple[str, str, str]]) -> list[list[dict]]:
    """Lay the sequences out over the key positions, row by row."""
    cells: list[dict] = []
    for _name, seq, binding in sequences:
        cells.append({"t": sequence_legend(seq), "h": describe(binding)})
    if len(cells) > TOTAL_POSITIONS:
        raise SystemExit(
            f"too many sequences ({len(cells)}) to fit {TOTAL_POSITIONS} positions"
        )
    while len(cells) < TOTAL_POSITIONS:
        cells.append({"t": ""})

    rows: list[list[dict]] = []
    offset = 0
    for size in ROW_SIZES:
        rows.append(cells[offset : offset + size])
        offset += size
    return rows


def yaml_dump_layers(layers: dict[str, list[list[dict]]]) -> str:
    """Emit a minimal `layers:` YAML document by hand.

    Hand-rolled so the output has no dependency on PyYAML and stays stable in
    diffs.
    """

    def q(value: str) -> str:
        # Always quote: legends contain punctuation and colons.
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    lines = ["# GENERATED FILE - do not edit by hand.", "# Regenerate with ./generate_leader_yaml.py", "layers:"]
    for name, rows in layers.items():
        lines.append(f"  {name}:")
        for row in rows:
            items = []
            for cell in row:
                if cell.get("t"):
                    items.append(
                        f"{{t: {q(cell['t'])}, h: {q(cell.get('h', ''))}}}"
                    )
                else:
                    items.append("{}")
            lines.append("  - [" + ", ".join(items) + "]")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default="config/keymap")
    ap.add_argument("--out", default="config/leader.yaml")
    args = ap.parse_args()

    src_path = Path(args.source)
    if not src_path.is_file():
        print(f"error: {src_path} not found", file=sys.stderr)
        return 1
    src = src_path.read_text()

    layers: dict[str, list[list[dict]]] = {}
    for instance, title in LAYER_TITLES.items():
        block = extract_behavior_block(src, instance)
        if block is None:
            print(f"warning: no '{instance}' behavior found, skipping", file=sys.stderr)
            continue
        sequences = parse_sequences(block)
        if not sequences:
            print(f"warning: no sequences in '{instance}', skipping", file=sys.stderr)
            continue
        layers[title] = build_layer(sequences)

    if not layers:
        print("error: no leader sequences found", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    out_path.write_text(yaml_dump_layers(layers))
    counts = ", ".join(f"{k}: {sum(1 for r in v for c in r if c.get('t'))}" for k, v in layers.items())
    print(f"wrote {out_path} ({counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
