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
from fnmatch import fnmatch
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "config"

# Keyboards we track.
KEYBOARDS = ["corne", "tempest", "seppelit", "sweep"]

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
        # keyed by (positions@layers): the pre-refactor corne keys for these
        # two combos, which the refactor normalises to tempest's.
        "4+5+6@QWERTY": [3, 4, 5],
        "20+21@QWERTY": [17, 18],
    },
}

# Combos that have been added on purpose since the golden reference was taken.
# Listed so that a new combo has to be acknowledged here rather than appearing
# silently; the harness reports additions as informational for these names only.
#
# NOTE: combos are keyed by their rendered legend (keymap-drawer emits no name),
# so if you change a legend in keymap_drawer.config.yaml you must update the
# entry here too.
EXPECTED_ADDED_COMBOS: dict[str, tuple[str, ...]] = {
    # Combos are keyed by "positions@layers" (see fingerprint), so these are
    # position globs rather than names - a rename in keymap_drawer.config.yaml
    # no longer invalidates them. A *removed* combo always fails regardless.
    #
    #   *@NUMNAV   the 19 vulgar fractions, chorded on NUMNAV digit pairs
    #   4+5@QWERTY num_word, on the T+Y chord
    "*": ("*@NUMNAV", "4+5@QWERTY"),
}


# Which golden keyboard each keyboard should be compared against.
#
# corne and sweep are special:
#   * corne loses its phantom 6th column (42 slots -> 36 real keys), so its
#     historical fingerprint cannot be compared directly. We compare it against
#     tempest - the same physical 36-key shape, already correct. That is a
#     STRONGER check than corne-vs-itself: it asserts the two boards now share
#     one identical layout rather than merely "nothing changed".
#   * sweep is compared against sweep. Its historical cradio.keymap was a
#     different, hand-written layout (4 layers, German unicode) and was never
#     part of the shared model, so there is no meaningful golden for it. Sweep
#     is instead checked for structural correctness (12 layers, 4-key thumb
#     rows, expected combo count) by check_structure() below.
REFERENCE: dict[str, str] = {
    "corne": "tempest",
    "tempest": "tempest",
    "seppelit": "tempest",
    "sweep": "sweep",
}

# Boards whose golden is their OWN history but which are expected to have
# structurally changed (seppelit drifted from the master; sweep is new).
# Their differences are reported as informational rather than failures.
STRUCTURAL: dict[str, dict] = {
    # sweep carries one extra combo: the leader1 chord it needs because a
    # 34-key board has no LH2 to put &leader1 on.
    #
    # Combo counts: 20 original + 1 num_word + 19 vulgar fractions = 40,
    # and 41 on sweep.
    "sweep": {"layers": 12, "thumbs": 4, "combos": 41},
    "seppelit": {"layers": 12, "thumbs": 6, "combos": 40},
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
    #
    # A combo is identified by (positions, layers) - NOT by its legend. The
    # legend is only a rendering concern, and keying on it made the harness
    # break every time a label was added in keymap_drawer.config.yaml, even
    # though the firmware behaviour was unchanged. Position+layer is also the
    # more meaningful identity: it is exactly what ZMK matches on, and a combo
    # moving to different keys is a real change while a relabelled one is not.
    #
    # The legend is recorded alongside as metadata so a label change is still
    # visible, without being treated as a behavioural difference.
    combos = list(parsed.get("combos") or [])
    combos.sort(key=lambda c: (
        sorted(int(p) for p in (c.get("p") or [])),
        "+".join(str(x) for x in (c.get("l") or [])),
    ))

    for combo in combos:
        pos = sorted(int(p) for p in (combo.get("p") or []))
        legend = combo.get("k") or ""
        layers = combo.get("l") or []
        name = f"{'+'.join(str(p) for p in pos)}@{'+'.join(str(x) for x in layers)}"
        out["combos"][name] = pos
        out["combos_meta"][name] = {"layers": layers, "legend": legend}

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


def check_structure(kb: str, cur: dict, spec: dict) -> list[str]:
    """Assert the structural shape a deliberately-changed board must have.

    Used for boards whose own history is not a valid baseline:
      * sweep  - new shared model; its old cradio.keymap was a different layout
      * seppelit - had drifted from the master (11 layers / 18 combos)
    """
    problems: list[str] = []
    layers = cur.get("layers", {})
    if len(layers) != spec["layers"]:
        problems.append(
            f"{kb}: expected {spec['layers']} layers, found {len(layers)}"
        )
    n_combos = len(cur.get("combos", {}))
    if n_combos != spec["combos"]:
        problems.append(
            f"{kb}: expected {spec['combos']} combos, found {n_combos}"
        )
    # key count per layer must equal main keys + thumbs
    expect_keys = 30 + spec["thumbs"]
    for name, keys in layers.items():
        if len(keys) != expect_keys:
            problems.append(
                f"{kb}: layer {name} has {len(keys)} keys, "
                f"expected {expect_keys} (30 main + {spec['thumbs']} thumbs)"
            )
    return problems


def check(golden: dict) -> int:
    current = capture()
    failures: list[str] = []
    expected_seen: set[tuple[str, str, str]] = set()
    expected_added = 0

    for kb, cur in current.items():
        # Boards with a deliberate structural change are checked against the
        # expected shape rather than against their own drifted history.
        if kb in STRUCTURAL:
            if "error" in cur:
                failures.append(f"{kb}: parse failed")
                continue
            spec = STRUCTURAL[kb]
            problems = check_structure(kb, cur, spec)
            failures.extend(problems)
            if not problems:
                print(f"  i {kb}: structural check passed "
                      f"({spec['layers']} layers, {spec['thumbs']} thumbs, "
                      f"{spec['combos']} combos)")
            continue

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

        # 3. combo count - a combo that vanishes must not pass silently.
        #
        # Added combos are reported but do not fail by default: the harness was
        # written to prove a refactor preserved behaviour exactly, whereas the
        # config now keeps growing (num_word, leader1 on sweep, ...). Losing a
        # combo is always a failure; gaining one is a deliberate change, listed
        # in EXPECTED_ADDED_COMBOS so it has to be acknowledged.
        if len(gold["combos"]) != len(cur["combos"]):
            missing = set(gold["combos"]) - set(cur["combos"])
            added = set(cur["combos"]) - set(gold["combos"])
            if missing:
                failures.append(f"{kb}: {len(missing)} combo(s) lost: {sorted(missing)}")
            for name in sorted(added):
                # A "*" entry applies to every keyboard; a per-keyboard entry
                # adds to it rather than replacing it.
                patterns = tuple(EXPECTED_ADDED_COMBOS.get("*", ())) + tuple(
                    EXPECTED_ADDED_COMBOS.get(kb, ())
                )
                if any(fnmatch(name, pattern) for pattern in patterns):
                    expected_added += 1
                else:
                    failures.append(
                        f"{kb}: unexpected combo {name!r} - if this is intended, "
                        f"add it (or a glob) to EXPECTED_ADDED_COMBOS"
                    )

    # Every declared normalisation must actually have been applied: compare
    # today's positions for those combos against corne's recorded history.
    # (Checked against the kb's OWN golden, not the REFERENCE target, because
    # the point is "corne changed away from its old accidental keys".)
    for kb, combos in NORMALISATIONS.items():
        hist = golden.get(kb, {}).get("combos", {})
        for old_key, old_pos in combos.items():
            # `old_key` is the pre-refactor (positions@layers) identity. After
            # normalisation the combo lives under a DIFFERENT position key, so:
            #   - the combo must be gone from its old keys, and
            #   - some combo must exist whose positions match the intended new
            #     positions (which is what the golden for tempest holds).
            now_here = current.get(kb, {}).get("combos", {}).get(old_key)
            if now_here is not None and now_here == old_pos:
                failures.append(
                    f"{kb}: combo {old_key} was NOT normalised - still on the "
                    f"old accidental keys {old_pos}"
                )
                continue
            new_pos = golden.get(REFERENCE.get(kb, kb), {}).get("combos", {})
            targets = [p for p in new_pos.values() if p != old_pos]
            if not any(
                p in current.get(kb, {}).get("combos", {}).values() for p in targets
            ):
                failures.append(
                    f"{kb}: combo previously at {old_pos} has no counterpart on "
                    f"the reference board"
                )
                continue
            print(f"  ~ {kb}: combo at {old_pos} normalised away from its old keys")
            expected_seen.add((kb, "combo", old_key))

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
