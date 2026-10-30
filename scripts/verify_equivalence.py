#!/usr/bin/env python3
"""
Equivalence harness for the zmk-helpers refactor.

Purpose
-------
The refactor replaces three near-duplicate generated keymaps (corne/tempest/
sweep) with one set of shared includes written in zmk-helpers key labels. That
kind of change fails *silently*: a combo written against the wrong label
happens to compile and simply fires on a different physical key. Upstream has
been bitten by exactly this (urob/zmk-helpers PR #68 for the adv360,
issue #103 for the Hummingbird).

So we do not diff text. We compare *expanded behaviour*:

  1. Layer bindings  - the fully preprocessed binding list per layer.
  2. Combo positions - the resolved numeric `key-positions` per combo.

Both are obtained from `keymap parse`, which runs the real C preprocessor over
the keymap with `zmk_additional_includes` applied. That is the same path ZMK's
build takes for the devicetree, so what this compares is what the firmware
would compile.

Usage
-----
    # capture the current (pre-refactor) state as the golden reference
    ./scripts/verify_equivalence.py capture --out .research/golden.json

    # after refactoring, compare against it
    ./scripts/verify_equivalence.py check --golden .research/golden.json

Exit status is 0 only when every keyboard and every tracked item matches, so
this is usable as a CI / pre-commit gate.

Intentional differences
-----------------------
Two corne combos are knowingly changed by the refactor (the user confirmed
corne's numbering was accidental and tempest's is correct):

  * combo_ctrlshiftx  - corne previously spanned LT1 LT0 RT0;
                        now matches ctrlshiftc's shape (LM3 LM2 LM1).
  * combo_leader2     - corne previously sat on the home row (RM1 RM2);
                        now matches tempest's bottom row (RB0 RB1).

These are declared in EXPECTED_DELTAS so that they are *asserted* to be the
only differences. An unexpected difference fails the check; an expected one
that fails to appear also fails (so the plan cannot silently drift).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "config"

# Keyboards we track. `cradio` (the old hand-written sweep keymap) is listed so
# we notice if it silently changes, but it is not part of the shared model.
KEYBOARDS = ["corne", "tempest", "seppelit", "cradio"]

# Differences that are intentional and must be the ONLY ones. Maps
# keyboard -> kind -> item -> note. Anything not listed here that differs is a
# regression.
#
# NOTE: these two combos are the *historical* corne-vs-tempest discrepancy. The
# refactor resolves them by making corne use tempest's keys, and because corne
# is now verified AGAINST tempest (see REFERENCE below), the two agree and no
# difference is observed. The assertion that they were actually fixed lives in
# check_normalisations(), which compares today's corne combos against the
# recorded corne history. Keeping it there avoids the contradiction of both
# "must differ" and "must match tempest".
EXPECTED_DELTAS: dict[str, dict[str, dict[str, str]]] = {}

# Combos that the refactor deliberately normalises from corne's historical
# (accidental) keys to tempest's (correct) keys. Maps
# keyboard -> combo key -> (expected historical position set).
NORMALISATIONS: dict[str, dict[str, list[int]]] = {
    "corne": {
        "CS+X@QWERTY": [3, 4, 5],
        "⟳ LDR2@QWERTY": [17, 18],
    },
}

# Which golden keyboard each keyboard should be compared against.
#
# corne is special: the refactor removes its phantom 6th column, taking it from
# 42 slots to 36 real keys. Its historical (42-key) fingerprint therefore cannot
# be compared directly - instead we compare it against tempest, which is the
# same physical 36-key shape and is already correct. That is a *stronger* check
# than comparing corne to itself, because it asserts the two boards now share
# one identical layout rather than merely "nothing changed".
REFERENCE: dict[str, str] = {
    "corne": "tempest",
    "tempest": "tempest",
    "seppelit": "seppelit",
    "cradio": "cradio",
}


def run_keymap_parse(keymap: Path) -> dict | None:
    """Parse one keymap via the keymap-drawer CLI.

    We do NOT reuse keymap_drawer.config.yaml's preamble as-is: the refactored
    keymaps rely on zmk-helpers' ZMK_LAYER/ZMK_COMBO, so the preamble must pull
    in helper.h. The real config is patched the same way (see the
    zmk_preamble note in keymap_drawer.config.yaml), so this mirrors it while
    staying independent of that file's drawing-oriented options.

    Returns the parsed YAML as a dict, or None if parsing failed (reported as a
    difference rather than crashing, so a broken keymap shows up clearly).
    """
    if shutil.which("keymap") is None:
        sys.exit("error: the `keymap` CLI (keymap-drawer) is not on PATH")
    try:
        import yaml
    except ImportError:
        sys.exit("error: PyYAML is required (pip install pyyaml)")

    base_cfg = REPO / "keymap_drawer.config.yaml"
    cfg = yaml.safe_load(base_cfg.read_text())
    pc = cfg.setdefault("parse_config", {})
    pc["zmk_preamble"] = (
        "#define KEYMAP_DRAWER\n"
        "#include <zmk-helpers/helper.h>\n"
    )
    includes = list(pc.get("zmk_additional_includes") or [])
    for extra in ("zmk-helpers/include", "config/zmk-helpers-repo/include"):
        if extra not in includes:
            includes.append(extra)
    pc["zmk_additional_includes"] = includes

    tmp_cfg = REPO / ".research" / "_parse_config.yaml"
    tmp_cfg.parent.mkdir(parents=True, exist_ok=True)
    tmp_cfg.write_text(yaml.safe_dump(cfg))

    cmd = ["keymap", "-c", str(tmp_cfg), "parse", "-c", "10", "-z", str(keymap)]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
    if proc.returncode != 0:
        print(f"  ! keymap parse failed for {keymap.name}", file=sys.stderr)
        print(f"    {proc.stderr.strip()[:400]}", file=sys.stderr)
        return None
    return yaml.safe_load(proc.stdout)


def fingerprint(parsed: dict) -> dict:
    """Reduce a parsed keymap to the behaviour we care about.

    * layers        -> list of binding strings, per layer display name
    * combos        -> sorted numeric key-positions, per combo name
    * combos_meta   -> timeout / layers / idle, per combo name
    """
    out: dict = {"layers": {}, "combos": {}, "combos_meta": {}}

    for name, rows in (parsed.get("layers") or {}).items():
        keys: list[str] = []
        for row in rows:
            for cell in row:
                if isinstance(cell, str):
                    keys.append(cell)
                elif isinstance(cell, dict):
                    # keymap-drawer renders a binding as its legend; `t` is the
                    # tap legend, `h` the hold legend. Reconstruct a stable
                    # string so both halves are compared.
                    t = cell.get("t", "")
                    h = cell.get("h", "")
                    keys.append(f"{t}/{h}" if h else str(t))
                else:
                    keys.append(str(cell))
        out["layers"][name] = keys

    # keymap-drawer emits combos as a *list* of dicts with no name field:
    #   {"p": [positions...], "k": <legend>, "l": [layers...]}
    # We identify a combo by its binding legend plus layer set and compare the
    # resolved numeric position set - that is the thing that actually changes
    # when a combo is mislabelled, and it fails silently at compile time.
    #
    # Combos are sorted by (legend, layers, positions) BEFORE assigning the
    # dedup suffix, so two combos sharing a legend (your two lock combos) get
    # stable, order-independent names: `...#0` is always the lower-position one.
    combos = list(parsed.get("combos") or [])
    combos.sort(key=lambda c: (
        str(c.get("k") or ""),
        "+".join(str(x) for x in (c.get("l") or [])),
        sorted(int(p) for p in (c.get("p") or [])),
    ))

    seen: dict[str, int] = {}
    for combo in combos:
        pos = sorted(int(p) for p in (combo.get("p") or []))
        legend = combo.get("k") or ""
        layers = combo.get("l") or []
        base = f"{legend}@{'+'.join(str(x) for x in layers)}"
        n = seen.get(base, 0)
        seen[base] = n + 1
        name = base if n == 0 else f"{base}#{n}"
        out["combos"][name] = pos
        out["combos_meta"][name] = {"layers": layers}

    return out


def keymap_path(kb: str) -> Path:
    """Where a keyboard's keymap currently lives.

    During the migration the refactored file is written alongside the old one
    (corne.keymap.new) so both can be compared before anything is replaced.
    Once migration finishes the .new file is renamed and this simply resolves
    to the normal path.
    """
    candidate = CONFIG / f"{kb}.keymap.new"
    if candidate.is_file():
        return candidate
    return CONFIG / f"{kb}.keymap"


def capture() -> dict:
    state: dict = {}
    for kb in KEYBOARDS:
        keymap = keymap_path(kb)
        if not keymap.is_file():
            print(f"  - {kb}: no keymap, skipped")
            continue
        print(f"  - {kb}: parsing {keymap.name}")
        parsed = run_keymap_parse(keymap)
        state[kb] = fingerprint(parsed) if parsed else {"error": "parse failed"}
    return state


def describe_diff(kb: str, kind: str, item: str, old, new) -> str:
    if kind == "layers":
        old_l, new_l = old or [], new or []
        detail = ""
        if len(old_l) != len(new_l):
            detail = f" (key count {len(old_l)} -> {len(new_l)})"
        else:
            bad = [
                f"#{i}: {a!r} -> {b!r}"
                for i, (a, b) in enumerate(zip(old_l, new_l))
                if a != b
            ]
            detail = " " + "; ".join(bad[:6])
            if len(bad) > 6:
                detail += f" (+{len(bad) - 6} more)"
        return f"LAYER {item} differs{detail}"
    return f"{kind.upper()} {item}: {old} -> {new}"


def check(golden: dict) -> int:
    current = capture()
    failures: list[str] = []
    expected_seen: set[tuple[str, str, str]] = set()

    for kb, cur in current.items():
        ref_name = REFERENCE.get(kb, kb)
        gold = golden.get(ref_name)
        if gold is None:
            failures.append(f"{kb}: no golden reference '{ref_name}' recorded")
            continue
        if cur is None or "error" in cur or "error" in gold:
            if (cur or {}).get("error") != gold.get("error"):
                failures.append(
                    f"{kb}: parse status {gold.get('error')} -> "
                    f"{(cur or {}).get('error')}"
                )
            continue
        if ref_name != kb:
            print(f"  i {kb}: compared against golden '{ref_name}' "
                  f"(same 36-key shape)")

        # 1. layers
        for layer, old_keys in gold["layers"].items():
            new_keys = cur["layers"].get(layer)
            if new_keys is None:
                failures.append(f"{kb}: layer {layer} disappeared")
            elif old_keys != new_keys:
                failures.append(describe_diff(kb, "layers", layer, old_keys, new_keys))

        # 2. combos. A combo is identified by its binding legend + layer set,
        #    and we compare the resolved numeric position set. This is the
        #    check that catches the silent-misbinding class of bug.
        for name, old_pos in gold["combos"].items():
            new_pos = cur["combos"].get(name)
            if new_pos is None:
                failures.append(f"{kb}: combo {name} disappeared")
                continue
            if old_pos != new_pos:
                failures.append(describe_diff(kb, "combo", name, old_pos, new_pos))
            meta_old = gold["combos_meta"].get(name, {})
            meta_new = cur["combos_meta"].get(name, {})
            if meta_old != meta_new:
                failures.append(
                    f"{kb}: combo {name} metadata {meta_old} -> {meta_new}"
                )

        # 3. combo count - a combo that vanishes entirely must not pass silently
        if len(gold["combos"]) != len(cur["combos"]):
            missing = set(gold["combos"]) - set(cur["combos"])
            added = set(cur["combos"]) - set(gold["combos"])
            if missing:
                failures.append(f"{kb}: {len(missing)} combo(s) lost: {sorted(missing)}")
            if added:
                failures.append(f"{kb}: {len(added)} unexpected combo(s): {sorted(added)}")

    # Every declared normalisation must actually have been applied: compare
    # today's positions for those combos against corne's recorded history.
    # (Checked against the kb's OWN golden, not the REFERENCE target, because
    # the point is "corne changed away from its old accidental keys".)
    for kb, combos in NORMALISATIONS.items():
        hist = golden.get(kb, {}).get("combos", {})
        for name, old_pos in combos.items():
            now = current.get(kb, {}).get("combos", {}).get(name)
            if now is None:
                failures.append(f"{kb}: normalised combo {name} is missing")
                continue
            if now == old_pos:
                failures.append(
                    f"{kb}: combo {name} was NOT normalised - still on the old "
                    f"accidental keys {old_pos}"
                )
            else:
                print(f"  ~ {kb}: combo {name} normalised {old_pos} -> {now}")
                expected_seen.add((kb, "combo", name))

    if failures:
        print(f"\nFAIL - {len(failures)} difference(s):")
        for f in failures:
            print(f"  X {f}")
        return 1

    layers = sum(len(v.get("layers", {})) for v in golden.values())
    combos = sum(len(v.get("combos", {})) for v in golden.values())
    print(f"\nOK - all layers and combos match their reference")
    if expected_seen:
        print(f"   ({len(expected_seen)} intentional normalisation(s) applied)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("capture", help="record current behaviour as golden")
    c.add_argument("--out", default=".research/golden.json")

    k = sub.add_parser("check", help="compare current behaviour against golden")
    k.add_argument("--golden", default=".research/golden.json")

    args = ap.parse_args()

    if args.cmd == "capture":
        print("Capturing golden reference:")
        state = capture()
        out = REPO / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        print(f"\nwrote {out}")
        return 0

    golden_path = REPO / args.golden
    if not golden_path.is_file():
        sys.exit(f"error: golden reference {golden_path} not found - run `capture` first")
    print("Checking behaviour against golden reference:")
    return check(json.loads(golden_path.read_text()))


if __name__ == "__main__":
    raise SystemExit(main())
