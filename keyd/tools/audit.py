#!/usr/bin/env python3
"""Structural audit of keyd/pt_pt.conf.

keyd's own `keyd check` validates syntax only - it accepts a config that binds a
key twice (last wins, silently), references a layer that does not exist until
run time in some paths, or leaves a layer unreachable. This script checks the
things keyd check does not:

  * duplicate key bindings within one layer
  * layer references that do not resolve
  * layers that nothing reaches (dead layers)
  * key names that are not in keyd's keycode table
  * chord key names that are not valid
  * more than keyd's MAX_LAYERS

Run from the repo root:  python3 keyd/tools/audit.py
Exits 1 if any check fails.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONF = ROOT / "keyd/pt_pt.conf"
KEYD_SRC = ROOT / ".research/keyd-src"
KEYS_C = KEYD_SRC / "src/keys.c"
CONFIG_H = KEYD_SRC / "src/config.h"

# Layers keyd provides itself; they always exist.
BUILTIN = {"main", "shift", "control", "alt", "meta", "altgr"}
# A [x:layout] section also makes x itself a layer name, and the layout file
# conventionally names its modifier sub-layers "<x>_shift"/"<x>_altgr". keyd
# registers those as ordinary named layers, so a layer(x_shift) reference is
# valid even though no [x_shift] section exists in this file.
IMPLICIT_SUFFIXES = ("_shift", "_altgr")


def load_key_names() -> set[str]:
    """Every key name keyd's keycode_table accepts.

    src/keys.c defines keycode_table[] with entries of the form
    [KEYD_X] = { "name", "alt_name", "shifted_name" }. All three are valid
    spellings in a config.
    """
    names: set[str] = set()
    text = KEYS_C.read_text(encoding="utf-8", errors="replace")
    # Each table entry looks like one of
    #     [KEYD_ESC] = { "esc", "escape", NULL },
    #     [KEYD_MUTE] = { "mute", NULL, NULL },
    # so the alt names may be quoted strings or the bare token NULL. Parse the
    # braced body and take every quoted string out of it.
    for m in re.finditer(r"\[KEYD_\w+\]\s*=\s*\{([^}]*)\}", text):
        for name in re.findall(r'"([^"]*)"', m.group(1)):
            if name and name != "NULL":
                names.add(name)
    # keyd also accepts bare single characters as key names, and the modifier
    # layer names it defines itself (src/config.c default_config), which are
    # valid on the left-hand side of a binding.
    names.update("abcdefghijklmnopqrstuvwxyz0123456789")
    names.update(".,-/;'[]\\`=")
    names.update({"shift", "control", "alt", "meta", "altgr"})
    return names


def max_layers() -> int:
    text = CONFIG_H.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"#define\s+MAX_LAYERS\s+(\d+)", text)
    return int(m.group(1)) if m else 32


def parse_layers(text: str) -> dict[str, list[tuple[int, str, str]]]:
    """Return {layer: [(lineno, key, value), ...]}.

    A line "key = value" inside a section binds key. A line "a+b = value" is a
    chord and is recorded under the key "a+b". Comments and blanks are skipped.
    """
    layers: dict[str, list[tuple[int, str, str]]] = {}
    current: str | None = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            layers.setdefault(current, [])
            continue
        if "=" not in line or current is None:
            continue
        # A key may itself be "=" or "-" (keyd names keys after the character
        # they produce), so partition on the LAST "=" rather than the first:
        # "= = <" binds the "=" key to "<".
        key, _, value = line.rpartition("=")
        layers[current].append((lineno, key.strip(), value.strip()))
    return layers


def layer_refs(value: str) -> list[str]:
    """Layer names referenced by a binding value.

    Several actions take a layer argument: layer(), oneshot(), toggle(),
    overload()/overloadt()/overloadi() (first argument), lettermod() (first
    argument). All of them count as reachability edges.
    """
    refs: list[str] = []
    for fn in ("layer", "oneshot", "toggle", "overload", "overloadt",
               "overloadi", "lettermod"):
        for m in re.finditer(rf"{fn}\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*[,)]", value):
            refs.append(m.group(1))
    return refs


def main() -> int:
    if not CONF.exists():
        print(f"FATAL: {CONF} does not exist", file=sys.stderr)
        return 1

    text = CONF.read_text(encoding="utf-8")
    layers = parse_layers(text)
    valid_keys = load_key_names()
    limit = max_layers()

    failures: list[str] = []
    warnings: list[str] = []

    # ---- layer count -----------------------------------------------------
    plain = [name for name in layers
             if ":" not in name and name not in ("ids", "global", "aliases")]
    if len(plain) > limit:
        failures.append(
            f"{len(plain)} layers defined, keyd allows {limit} (config.h)"
        )

    # ---- colon-suffixed layer names (silently discarded by keyd) ----------
    # config_add_layer (src/config.c:443-461) does name = strtok(buf, ":") and
    # returns 1 as soon as that name already exists. So a section whose name
    # contains ":" is only valid when the prefix is NOT already a layer - and
    # when it IS, keyd discards the section entirely and merges its bindings
    # into the prefix layer, last binding winning. keyd check does NOT catch
    # this. Real defect class found by adversarial review (D1).
    seen_names: set[str] = set()
    for name in layers:
        if ":" in name and name not in ("ids", "global", "aliases"):
            prefix = name.split(":", 1)[0]
            if prefix in seen_names or prefix in layers:
                failures.append(
                    f"[{name}]: keyd will silently DISCARD this layer and merge "
                    f"its bindings into [{prefix}] (config_add_layer early "
                    f"return), so the last binding wins. Use a composite layer "
                    f"[{prefix}+<modifier>] instead."
                )
        seen_names.add(name)

    # ---- duplicate bindings within a layer -------------------------------
    for name, entries in layers.items():
        if name in ("ids", "global", "aliases"):
            continue
        seen: dict[str, int] = {}
        for lineno, key, _ in entries:
            if key in seen:
                failures.append(
                    f"[{name}] line {lineno}: key {key!r} already bound on line "
                    f"{seen[key]} (keyd keeps only one, silently)"
                )
            else:
                seen[key] = lineno

    # ---- layer references resolve ----------------------------------------
    for name, entries in layers.items():
        if name in ("ids", "global", "aliases"):
            continue
        for lineno, key, value in entries:
            for ref in layer_refs(value):
                bases = {n.split(":")[0] for n in layers}
                if (ref not in layers and ref not in BUILTIN
                        and not any(ref.endswith(sfx) and
                                    ref[: -len(sfx)] in bases
                                    for sfx in IMPLICIT_SUFFIXES)):
                    failures.append(
                        f"[{name}] line {lineno}: layer({ref}) does not exist"
                    )

    # ---- dead layers ------------------------------------------------------
    reachable: set[str] = set()
    # [main] is always active. Layout and modifier layers are entered by keyd.
    stack = ["main"]
    for name in layers:
        if name.startswith("pt") or ":" in name:
            stack.append(name)
    while stack:
        cur = stack.pop()
        if cur in reachable:
            continue
        reachable.add(cur)
        for _, _, value in layers.get(cur, []):
            for ref in layer_refs(value):
                if ref not in reachable:
                    stack.append(ref)
    for name in plain:
        if name not in reachable:
            warnings.append(f"[{name}] is not reachable from [main]")

    # ---- key names --------------------------------------------------------
    for name, entries in layers.items():
        if name in ("ids", "global", "aliases"):
            continue
        for lineno, key, value in entries:
            for part in key.split("+"):
                part = part.strip()
                if part not in valid_keys:
                    failures.append(
                        f"[{name}] line {lineno}: {part!r} is not a keyd key name"
                    )
            # A binding value that is a bare key name must also be valid.
            bare = value.strip()
            # A modifier-prefixed sequence (C-a, A-M-x) is a macro, not a key.
            if "-" in bare:
                continue
            if re.fullmatch(r"[A-Za-z0-9_.,\-/;'\[\]\\`=]+", bare) and \
               not any(bare.startswith(p) for p in
                       ("layer(", "macro(", "command(", "noop", "oneshot(",
                        "overload(", "overloadt(", "overloadi(", "lettermod(",
                        "toggle(", "setlayout(", "swap(")):
                if bare not in valid_keys:
                    failures.append(
                        f"[{name}] line {lineno}: value {bare!r} is not a keyd "
                        "key name"
                    )

    # ---- composite layers are reached by activation, not by layer() -------
    # A composite layer [a+b] becomes active when BOTH a and b are active; no
    # binding ever references it by name (config.c:393-420). Warning about
    # unreachability for those is a false positive.
    composites = {n for n in layers if "+" in n and ":" not in n}
    warnings[:] = [w for w in warnings
                   if not any(f"[{c}]" in w for c in composites)]

    # ---- report ----------------------------------------------------------
    print(f"keyd/pt_pt.conf: {len(text.splitlines())} lines, "
          f"{len(plain)} plain layers of {limit} allowed")
    print(f"  sections: {', '.join(sorted(n for n in layers if n not in ('ids','global')))}")

    if failures:
        print(f"\n{len(failures)} FAILURE(S):", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
    if warnings:
        print(f"\n{len(warnings)} warning(s):", file=sys.stderr)
        for w in warnings:
            print(f"  {w}", file=sys.stderr)
    if not failures:
        print("\nAll structural checks passed.")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
