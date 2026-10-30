#!/usr/bin/env python3
"""
Generate a keymap-drawer "virtual layer" YAML describing the leader-key
sequences, so keymap-drawer can render them (it cannot discover them itself:
leader sequences are properties of a behavior, not key bindings).

Everything is derived from config/include/behaviors.dtsi - the single source of truth. Do not
edit the generated file (config/leader.yaml) by hand; edit config/include/behaviors.dtsi and
re-run this script (generate_keymaps.sh does that automatically).

Usage:
    ./generate_leader_yaml.py [--source config/include/behaviors.dtsi] [--out config/leader.yaml]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from string import ascii_lowercase

# Row shapes per keyboard, used when --rows is not given explicitly.
# These must match the physical layout the drawing is rendered against.
KEYBOARD_ROWS: dict[str, list[int]] = {
    "tempest": [10, 10, 10, 6],       # 36 keys, 3x5 + 3 thumbs per side
    "seppelit": [10, 10, 10, 6],      # 36 keys
    "corne": [10, 10, 10, 10, 2],     # 42 keys, 3x6 + 3 thumbs per side
}
DEFAULT_ROWS = [10, 10, 10, 6]

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


def build_layer(
    sequences: list[tuple[str, str, str]], row_sizes: list[int]
) -> list[list[dict]]:
    """Lay the sequences out over the key positions, row by row.

    Sequences are sorted alphabetically by their displayed legend, then placed
    starting at the top row's left-most key and continuing left to right, row by
    row, down to the bottom row. (Within a row the first half of the cells is
    the left hand and the second half the right hand, so filling sequentially
    reads left-to-right across the whole keyboard.)

    Callers hand in at most `total` sequences; use build_layers() to paginate a
    longer list across several layers.
    """
    total = sum(row_sizes)

    ordered = sorted(sequences, key=lambda s: sequence_legend(s[1]))

    cells: list[dict] = []
    for _name, seq, binding in ordered:
        cells.append({"t": sequence_legend(seq), "h": describe(binding)})
    if len(cells) > total:
        raise SystemExit(
            f"internal error: build_layer got {len(cells)} sequences for "
            f"{total} positions - use build_layers() to paginate"
        )
    while len(cells) < total:
        cells.append({"t": ""})

    rows: list[list[dict]] = []
    offset = 0
    for size in row_sizes:
        rows.append(cells[offset : offset + size])
        offset += size
    return rows


def build_layers(
    sequences: list[tuple[str, str, str]], row_sizes: list[int], title: str
) -> dict[str, list[list[dict]]]:
    """Fit `sequences` into one or more layers of `row_sizes` capacity.

    A leader behavior can hold more sequences than the board has keys (leader1
    is at 39 while a 36-key board has 36 positions). That physical limit is
    irrelevant to the firmware - these are *virtual* layers rendered purely for
    the drawing - so rather than fail the build we paginate:
    LEADER1, LEADER1b, LEADER1c, ...

    Every sequence stays visible, nothing is silently dropped, and the firmware
    is untouched.
    """
    total = sum(row_sizes)
    if total <= 0:
        raise SystemExit(f"internal error: row shape {row_sizes} has no positions")

    ordered = sorted(sequences, key=lambda s: sequence_legend(s[1]))
    chunks = [ordered[i : i + total] for i in range(0, len(ordered), total)]
    if not chunks:
        return {}

    out: dict[str, list[list[dict]]] = {}
    for index, chunk in enumerate(chunks):
        # The first page keeps the plain name so existing drawings stay stable.
        # Later pages get a letter suffix: b, c, ... then b2, c2, ... once the
        # alphabet runs out, so an unusually long leader list degrades instead
        # of raising IndexError.
        if index == 0:
            name = title
        else:
            # Start at 'b' (not 'a') so the second page keeps the name it had
            # before pagination grew a wrap-around case.
            letter = ascii_lowercase[index % 26]
            cycle = index // 26
            name = f"{title}{letter}" if cycle == 0 else f"{title}{letter}{cycle + 1}"
        out[name] = build_layer(chunk, row_sizes)
    if len(chunks) > 1:
        print(
            f"note: {title} has {len(ordered)} sequences, more than this "
            f"board's {total} positions - split across {len(chunks)} layers "
            f"({', '.join(out)})",
            file=sys.stderr,
        )
    return out


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
    ap.add_argument("--source", default="config/include/behaviors.dtsi")
    ap.add_argument("--out", default="config/leader.yaml")
    ap.add_argument(
        "--keyboard",
        help="keyboard name; selects the row shape from KEYBOARD_ROWS",
    )
    ap.add_argument(
        "--rows",
        type=int,
        nargs="+",
        help="key positions per row, e.g. --rows 10 10 10 6. Overrides --keyboard.",
    )
    ap.add_argument(
        "--from-parsed",
        metavar="YAML",
        help="derive the row shape from a keymap-drawer parsed keymap YAML "
        "(the first layer's row sizes). Overrides --keyboard.",
    )
    args = ap.parse_args()

    if args.from_parsed:
        try:
            import yaml  # noqa: PLC0415  (optional dependency)
        except ImportError:
            print(
                "error: --from-parsed needs PyYAML (pip install pyyaml)",
                file=sys.stderr,
            )
            return 1
        try:
            parsed = yaml.safe_load(Path(args.from_parsed).read_text())
            first_layer = next(iter(parsed["layers"].values()))
            row_sizes = [len(r) for r in first_layer]
        except Exception as exc:  # noqa: BLE001
            print(f"error: could not read row shape from {args.from_parsed}: {exc}", file=sys.stderr)
            return 1
    elif args.rows:
        row_sizes = args.rows
    elif args.keyboard:
        row_sizes = KEYBOARD_ROWS.get(args.keyboard)
        if row_sizes is None:
            print(
                f"error: unknown keyboard '{args.keyboard}'; "
                f"known: {', '.join(KEYBOARD_ROWS)}. Use --rows to specify directly.",
                file=sys.stderr,
            )
            return 1
    else:
        row_sizes = DEFAULT_ROWS

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
        layers.update(build_layers(sequences, row_sizes, title))

    if not layers:
        print("error: no leader sequences found", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    out_path.write_text(yaml_dump_layers(layers))
    counts = ", ".join(f"{k}: {sum(1 for r in v for c in r if c.get('t'))}" for k, v in layers.items())
    print(f"wrote {out_path} (rows={row_sizes}, {counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
