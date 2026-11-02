#!/usr/bin/env python3
"""Measure keyd's Unicode coverage of the ZMK leader symbol sets.

Reads keyd's own compose table (.research/keyd-src/data/keyd.compose) and the
generated ZMK leader sequence files, and reports which code points keyd can
actually emit. Used to write the honest coverage numbers in keyd/x390.conf.

Run from the repo root:  python3 keyd/tools/coverage.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / ".research/keyd-src/data/keyd.compose"
MATH = ROOT / "config/include/leader-math.dtsi"
EMOJI = ROOT / "config/include/leader-emoji.dtsi"

SEQ_RE = re.compile(
    r"\s*seq_(\S+)\s*\{\s*sequence\s*=\s*<([^>]*)>;\s*"
    r"bindings\s*=\s*<([^>]*)>;\s*\};\s*//\s*(.*)"
)
UC_RE = re.compile(r"&uc\s+(0x[0-9A-Fa-f]+)")


def load_compose():
    """Return the set of code points keyd emits via <Cancel>+3 base36 digits.

    ASCII is deliberately NOT in keyd's compose table: src/macro.c compiles a
    code point < 128 into a MACRO_KEYSEQUENCE looked up in keycode_table by
    name, not into a MACRO_UNICODE entry. So ASCII always works - and on a
    config that includes a "[xx:layout]" section it comes out as that
    layout's character. Only code points >= 128 need the compose table and the
    XCompose file. Seeding with range(128) models that correctly.
    """
    table = set(range(128))
    for line in COMPOSE.open(encoding="utf-8"):
        m = re.match(r'^<Cancel> <[^>]+> <[^>]+> <[^>]+> : "(.*)"\s*$', line)
        if m and len(m.group(1)) == 1:
            table.add(ord(m.group(1)))
    return table


def load_sequences(path):
    out = []
    for line in path.open(encoding="utf-8"):
        m = SEQ_RE.match(line)
        if m:
            out.append(
                (
                    m.group(1),
                    m.group(2).split(),
                    [int(c, 16) for c in UC_RE.findall(m.group(3))],
                    m.group(4).strip(),
                )
            )
    return out


def main():
    table = load_compose()
    print(f"keyd compose table: {len(table)} code points")
    rc = 0
    for tag, path in (("math", MATH), ("emoji", EMOJI)):
        seqs = load_sequences(path)
        cps = {c for s in seqs for c in s[2]}
        missing = sorted(c for c in cps if c not in table)
        ok = len(cps) - len(missing)
        print(
            f"{tag:6s} seqs={len(seqs):4d} distinct_cps={len(cps):4d} "
            f"emittable={ok:4d} missing={len(missing):3d}"
        )
        if missing:
            print("   missing: " + " ".join("U+%04X" % c for c in missing))
        rc += len(missing)
    return rc


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
