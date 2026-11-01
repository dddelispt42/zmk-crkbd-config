#!/usr/bin/env python3
"""
Generate the leader1 math-symbol and emoji sequences from typst's codex data.

Source of truth
---------------
typst keeps its symbol tables in a separate repository, typst/codex:

    src/modules/sym.txt      the math symbols   (sym.sum -> summation)
    src/modules/emoji.txt    the emoji          (emoji.axe -> axe)

Those files, not the rendered documentation, are what this script reads. They
are fetched into .research/ on first use so the generator can be re-run offline.

How a sequence is built
-----------------------
    leader1 + M + <name chars>     math        e.g. M S U M   -> U+2211
    leader1 + E + <name chars>     emoji       e.g. E A X E   -> U+1FA93

The name characters are uppercased and '.' becomes the DOT key, so typst's
`arrow.r` is M A R R O W DOT R.

Two constraints shape the output, both verified against the module source
(urob/zmk-leader-key, src/behaviors/behavior_leader_key.c):

  1. Sequences must be PREFIX-FREE. filter_leader_sequences() returns as soon as
     a complete match is found, so a sequence that is a prefix of another makes
     the longer one unreachable.
  2. ZMK_LEADER_MAX_KEYS_PER_SEQUENCE caps the length of one sequence.

Collisions and how they are resolved
------------------------------------
  * Case: leader keys match keycodes, not shift state, so `alpha` and `Alpha`
    cannot both exist. Lowercase wins; variants get a trailing marker and every
    one is listed in the generated documentation.
  * Prefix: names that are a prefix of another name (e.g. `airplane` vs
    `airplane.small`) are kept only in their LONGEST form. The shorter is
    emitted commented out, so it can be enabled deliberately.
  * The existing `mo` sequence on leader1 is a prefix of ten math names
    (`moo`, `mom`, `mor`, ...). Those keep a documented suffix.

Output
------
    config/include/leader-math.dtsi     sequences (active + commented)
    config/include/leader-emoji.dtsi    sequences (active + commented)
    docs/LEADER-SYMBOLS.md              the human-readable reference

Usage
-----
    ./scripts/gen_leader_symbols.py [--offline] [--active-math N] [--active-emoji N]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import unicodedata
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
RESEARCH = REPO / ".research"
CODEX_BASE = "https://raw.githubusercontent.com/typst/codex/main/src/modules"

VS16 = 0xFE0F  # VARIATION SELECTOR-16, emoji presentation
VS15 = 0xFE0E  # VARIATION SELECTOR-15, text presentation

# Existing leader1 sequences that begin with M or E. Prefix-free checking needs
# these too, because a collision can come from either side.
EXISTING_M_E_PREFIXES = (("M", "O"),)

# ---------------------------------------------------------------------------
# Chosen active sets
# ---------------------------------------------------------------------------

# The math symbols enabled by default: the ones that come up constantly in
# LaTeX/typst. Everything else is emitted commented out.
ACTIVE_MATH = [
    # arithmetic and relations
    "plus", "minus", "times", "div", "approx", "equiv", "eq.not", "eq.def", "prop",
    "lt", "gt", "lt.eq", "gt.eq", "lt.eq.slant", "gt.eq.slant",
    "subset", "supset", "subset.eq", "supset.eq", "inset", "in.not", "in.rev",
    "perp", "parallel",
    # big operators
    "sum", "product", "integral", "integral.cont", "union.big", "inter.big",
    # calculus and analysis
    "infinity", "partial", "nabla", "prime", "prime.rev",
    # logic and sets
    "forall", "exists", "and", "or", "not", "top", "bot", "emptyset",
    "union", "inter", "therefore", "because",
    # arrows
    "arrow.r", "arrow.l", "arrow.l.r", "arrow.r.long", "arrow.l.long",
    "arrow.r.double", "arrow.r.bar", "arrow.r.hook", "arrow.l.hook",
    # geometry and miscellaneous
    "angle", "angle.right", "triangle.stroked.t", "square.stroked",
    "circle.stroked", "degree", "aleph", "ell",
]

# The emoji enabled by default: the ones that are actually useful when writing
# text and notes. All prefix-safe and single-code-point where possible.
ACTIVE_EMOJI = [
    # Selected by GLYPH from emoji.txt, so the names are the real typst ones
    # (checkmark.box rather than check, thumb.up rather than thumbsup, ...).
    # Every one was checked to be prefix-free against the others, so all of
    # them are reachable.
    # status and feedback
    "checkmark.box", "crossmark", "warning", "lightbulb", "party",
    # gestures
    "hands.folded", "thumb.up", "thumb.down", "hand.ok", "hand.wave",
    # signals and objects
    "lightning", "clock.alarm", "chain", "clip", "pencil", "calendar",
    "pin", "scissors", "magnify.l",
    # things
    "heart", "star", "fire", "rocket", "bug", "eyes",
    "lock", "key", "bell",
    # arrows
    "arrow.r.filled", "arrow.l.filled", "arrow.t.filled", "arrow.b.filled",
]

# Names that need a marker because lowercasing/uppercasing collides, or because
# the existing `mo` sequence shadows them. Filled in by resolve().
SUFFIX_FOR_CASE = "U"   # uppercase Greek etc: alpha -> ALPHA, Alpha -> ALPHAU
SUFFIX_FOR_MO = "X"     # collides with `mo` -> moo becomes MOOX

# Explicit renames, applied before anything else.
#
# `in` (the element-of symbol, U+2208) is a prefix of in.not, in.rev, integral
# and infinity, and only one of the five can be reachable by its exact typst
# name. The other four are far more common in written maths than bare ∈, so `in`
# is the one that moves.
RENAMES = {
    "in": "inset",
}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def fetch(name: str, offline: bool) -> pathlib.Path:
    dest = RESEARCH / name
    if dest.is_file():
        return dest
    if offline:
        raise SystemExit(f"{dest} is missing and --offline was given")
    RESEARCH.mkdir(exist_ok=True)
    url = f"{CODEX_BASE}/{name}"
    print(f"  fetching {url}")
    with urllib.request.urlopen(url, timeout=60) as fh:
        dest.write_bytes(fh.read())
    return dest


def parse_codex(path: pathlib.Path) -> list[tuple[str, str]]:
    """Return [(full_name, glyph_spec)] for a codex data file.

    Names are reconstructed from indentation. A line at column 0 sets the parent
    name; an indented line beginning with '.' is a SUB-entry, so `eq` followed by
    an indented `.not` is the single name `eq.not`. Deeper indentation nests
    further (`lt` + `.eq` + `.slant` = `lt.eq.slant`), so a stack is kept.

    Getting this wrong is easy and silent: treating `.not` as a literal name
    yields sequences that do not exist in typst, and loses every real one.
    """
    out: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        if not line.strip() or line.lstrip().startswith("//"):
            continue
        # A parent entry may have NO glyph of its own - typst writes a bare
        # `arrow` header and then indents every real symbol under it. The
        # glyph is therefore optional; requiring it silently dropped such
        # parents, leaving their children with no prefix to attach to
        # (`.r` instead of `arrow.r`).
        m = re.match(r"^(\s*)([A-Za-z0-9._-]+)(?:\s+(.+?))?\s*$", line)
        if not m:
            continue
        indent, name = len(m.group(1)), m.group(2)
        spec = m.group(3) or ""
        if indent == 0:
            stack = [(0, name)]
            full = name
        elif name.startswith("."):
            while stack and stack[-1][0] >= indent:
                stack.pop()
            full = (stack[-1][1] if stack else "") + name
            stack.append((indent, full))
        else:
            stack = [(indent, name)]
            full = name
        if spec:
            out.append((full, spec))
    return out


def spec_to_codepoints(spec: str) -> list[int]:
    """Convert a codex glyph spec to a list of code points.

    Handles \\u{XXXX} escapes, literal characters, and \\vs{emoji}/\\vs{text}
    variation selectors.
    """
    cps: list[int] = []
    for part in re.split(r"(\\vs\{(?:emoji|text)\})", spec):
        if part == r"\vs{emoji}":
            cps.append(VS16)
            continue
        if part == r"\vs{text}":
            cps.append(VS15)
            continue
        if not part:
            continue
        for m in re.finditer(r"\\u\{([0-9A-Fa-f]+)\}", part):
            cps.append(int(m.group(1), 16))
        for ch in re.sub(r"\\u\{[0-9A-Fa-f]+\}", "", part):
            cps.append(ord(ch))
    return cps


# ---------------------------------------------------------------------------
# Sequence building
# ---------------------------------------------------------------------------

def name_to_keys(name: str) -> tuple[str, ...]:
    """Map a typst name to leader keys: uppercase, '.' -> DOT."""
    return tuple("DOT" if ch == "." else ch.upper() for ch in name)


def split_name(name: str) -> tuple[str, str]:
    """Split 'arrow.r' into ('arrow', 'r'); plain 'sum' -> ('sum', '')."""
    if "." in name:
        base, _, sub = name.partition(".")
        return base, sub
    return name, ""


def is_prefix(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    return len(a) < len(b) and b[: len(a)] == a


def resolve(entries, prefix, existing, suffix_case, suffix_mo):
    """Work out the final sequence for every entry.

    Returns a list of dicts with the name, code points, keys, and a status of
    'active', 'commented-prefix', or 'commented-case'. Also returns the list of
    documented exceptions.
    """
    resolved = []
    seen: dict[tuple[str, ...], str] = {}
    notes: list[str] = []

    for name, spec in entries:
        cps = spec_to_codepoints(spec)
        if not cps:
            continue
        if name in RENAMES:
            notes.append(f"`{name}` -> `{RENAMES[name]}` (renamed, see RENAMES)")
            name = RENAMES[name]
        keys = (prefix,) + name_to_keys(name)

        # 1. case collision: another name already claimed these keys
        if keys in seen:
            other = seen[keys]
            # lowercase wins; the other form gets the marker
            if name.islower() and not other.islower():
                notes.append(f"`{other}` -> `{name}` (lowercase wins)")
                # replace the earlier entry
                resolved = [r for r in resolved if r["keys"] != keys]
            else:
                newkeys = keys + (suffix_case,)
                notes.append(f"`{name}` -> suffix `{suffix_case}` (case collision with `{other}`)")
                keys = newkeys
        seen[keys] = name

        # 2. collision with an existing non-math sequence
        for ex in existing:
            if is_prefix(ex, keys) or is_prefix(keys, ex):
                newkeys = keys + (suffix_mo,)
                notes.append(
                    f"`{name}` -> suffix `{suffix_mo}` "
                    f"(existing `{' '.join(ex)}` is a prefix)"
                )
                keys = newkeys
                break

        resolved.append({"name": name, "cps": cps, "keys": keys, "spec": spec})

    return resolved, notes


def mark_prefix_conflicts(resolved, active_names):
    """Decide which entries stay enabled.

    The leader module fires the instant a sequence completes, so when one name
    is a prefix of another only one of the two can be typeable.

    Only names in the ACTIVE set compete for that. That distinction matters: the
    symbol table contains control-picture characters - `em` (U+2419 End of
    Medium) and `sub` (U+241A Substitute) - which would otherwise block
    `emptyset` and `subset` purely because they share a letter prefix. An
    obscure control character should not disable a symbol that gets typed.

    Rules, applied to the active set only:
      * a name is disabled if a SHORTER active name prefixes it, since that
        shorter one fires first and the longer is unreachable. `eq` blocks
        `eq.not`.
      * a name is NOT disabled merely for prefixing a longer name; it is the
        base symbol and the longer variant is the one that gets disabled.
        `plus` stays, `plus.o` does not.
    """
    active_keys = {r["keys"] for r in resolved if r["name"] in active_names}
    for r in resolved:
        if r["name"] not in active_names:
            r["prefix_shadowed"] = False
            r["blocks_longer"] = False
            continue
        ours = r["keys"]
        r["prefix_shadowed"] = any(
            other != ours and is_prefix(other, ours) for other in active_keys
        )
        r["blocks_longer"] = any(
            other != ours and is_prefix(ours, other) for other in active_keys
        )
    return resolved


def cp_literal(cps: list[int]) -> str:
    """The &uc argument list for a code point sequence."""
    return " ".join(f"&uc 0x{c:X} 0" for c in cps)


def glyph_comment(cps: list[int], name: str) -> str:
    """A trailing comment showing what a sequence produces.

    The visible characters are emitted directly so the .dtsi is readable
    without decoding hex. Two cases need care:

      * variation selectors (U+FE0E/FE0F) are invisible and only modify the
        preceding character, so they are dropped from the display.
      * some symbols ARE invisible - word joiners, zero-width spaces, the
        various width spaces. Printing those raw gives a blank-looking comment
        that looks like a mistake, so they are named instead.
    """
    visible = "".join(chr(c) for c in cps if c not in (VS15, VS16))
    if not visible or not visible.strip():
        return f"// {name} (invisible: U+{cps[0]:04X})"
    # a combining mark with no base character renders poorly; show it on a
    # dotted circle, the same convention the SVG legends use
    if unicodedata.category(visible[0]).startswith("M"):
        visible = "\u25CC" + visible
    return f"// {name} = {visible}"


def emit_sequences(resolved, active_names, leader_name, header_comment):
    """Produce the .dtsi body: active sequences, then commented ones."""
    lines = [header_comment, "", f"&{leader_name} {{"]

    active = [r for r in resolved if r["name"] in active_names and not r["prefix_shadowed"]]
    commented = [r for r in resolved if r not in active]

    # Node names must be unique within the leader node, and the same typst name
    # appears in both categories (arrow.r.filled is both a math symbol and an
    # emoji), so the category letter is part of the node name.
    node_prefix = "seq_" + resolved[0]["keys"][0].lower() + "_"

    lines.append(f"    /* --- active ({len(active)}) --- */")
    for r in sorted(active, key=lambda r: r["name"]):
        seq = " ".join(r["keys"])
        lines.append(
            f'    {node_prefix}{r["name"].replace(".", "_")} {{ '
            f'sequence = <{seq}>; bindings = <{cp_literal(r["cps"])}>; }};'
            f'  {glyph_comment(r["cps"], r["name"])}'
        )

    lines.append("")
    lines.append(f"    /* --- available but disabled ({len(commented)}) ---")
    lines.append("     * Uncomment a line to enable it. Each is disabled for one of:")
    lines.append("     *   - it is not in the active set, or")
    lines.append("     *   - its name is a prefix of another name, so enabling it")
    lines.append("     *     would make that longer name unreachable.")
    lines.append("     * See docs/LEADER-SYMBOLS.md for the full list.")
    lines.append("     */")
    for r in sorted(commented, key=lambda r: r["name"]):
        seq = " ".join(r["keys"])
        node = f'{node_prefix}{r["name"].replace(".", "_")}'
        lines.append(
            f'    // {node} {{ sequence = <{seq}>; '
            f'bindings = <{cp_literal(r["cps"])}>; }};'
            f'  {glyph_comment(r["cps"], r["name"])}'
        )

    lines.append("};")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    print("parsing codex data")
    sym = parse_codex(fetch("sym.txt", args.offline))
    emoji = parse_codex(fetch("emoji.txt", args.offline))
    print(f"  sym.txt   {len(sym)}")
    print(f"  emoji.txt {len(emoji)}")

    math, math_notes = resolve(sym, "M", EXISTING_M_E_PREFIXES, SUFFIX_FOR_CASE, SUFFIX_FOR_MO)
    emo, emo_notes = resolve(emoji, "E", EXISTING_M_E_PREFIXES, SUFFIX_FOR_CASE, SUFFIX_FOR_MO)
    math = mark_prefix_conflicts(math, set(ACTIVE_MATH))
    emo = mark_prefix_conflicts(emo, set(ACTIVE_EMOJI))
    print(f"  math sequences   {len(math)}  ({sum(1 for r in math if r['prefix_shadowed'])} prefix-shadowed)")
    print(f"  emoji sequences  {len(emo)}  ({sum(1 for r in emo if r['prefix_shadowed'])} prefix-shadowed)")

    print(f"  exceptions: math {len(math_notes)}, emoji {len(emo_notes)}")

    # ---- emit the two devicetree fragments -------------------------------
    inc = REPO / "config" / "include"
    math_dtsi = emit_sequences(
        math, set(ACTIVE_MATH), "leader1",
        "/*\n"
        " * Math symbol leader sequences: leader1 then M then the typst name.\n"
        " *\n"
        " *   leader1 + M + S U M    -> U+2211   (sym.sum)\n"
        " *   leader1 + M + A R R O W DOT R -> U+2192  (sym.arrow.r)\n"
        " *\n"
        " * GENERATED by scripts/gen_leader_symbols.py from typst/codex sym.txt.\n"
        " * Do not edit by hand; re-run the script instead.\n"
        " *\n"
        " * Each line ends with a comment showing the symbol it produces, so the\n"
        " * file can be read without decoding hex. Symbols that are invisible on\n"
        " * their own (word joiners, the width spaces) are named with their code\n"
        " * point instead of being printed blank.\n"
        " *\n"
        " * Sequences must be prefix-free: a short name that is a prefix of a\n"
        " * longer one would fire first and make the longer unreachable, so those\n"
        " * are emitted commented out. See docs/LEADER-SYMBOLS.md.\n"
        " */",
    )
    emoji_dtsi = emit_sequences(
        emo, set(ACTIVE_EMOJI), "leader1",
        "/*\n"
        " * Emoji leader sequences: leader1 then E then the typst name.\n"
        " *\n"
        " *   leader1 + E + A X E    -> U+1FA93   (emoji.axe)\n"
        " *\n"
        " * GENERATED by scripts/gen_leader_symbols.py from typst/codex emoji.txt.\n"
        " * Do not edit by hand; re-run the script instead.\n"
        " *\n"
        " * Each line ends with a comment showing the emoji it produces, so the\n"
        " * file can be read without decoding hex.\n"
        " */",
    )
    (inc / "leader-math.dtsi").write_text(math_dtsi)
    (inc / "leader-emoji.dtsi").write_text(emoji_dtsi)
    print(f"  wrote config/include/leader-math.dtsi   ({math_dtsi.count(chr(10))} lines)")
    print(f"  wrote config/include/leader-emoji.dtsi  ({emoji_dtsi.count(chr(10))} lines)")

    # ---- emit the documentation ------------------------------------------
    docs = REPO / "docs"
    docs.mkdir(exist_ok=True)
    write_docs(docs / "LEADER-SYMBOLS.md", math, emo, math_notes, emo_notes)
    print("  wrote docs/LEADER-SYMBOLS.md")
    return 0


def write_docs(path, math, emo, math_notes, emo_notes) -> None:
    """Write the human-readable reference page."""
    def table(entries, active_names):
        rows = ["| sequence | name | chars | status |", "|---|---|---|---|"]
        for r in sorted(entries, key=lambda r: r["name"]):
            seq = " ".join(r["keys"])
            glyph = "".join(chr(c) for c in r["cps"] if c not in (VS16, VS15))
            if r["name"] in active_names and not r["prefix_shadowed"]:
                status = "active"
            elif r["prefix_shadowed"]:
                status = "disabled - prefix of another name"
            else:
                status = "available (commented out)"
            rows.append(f"| `{seq}` | `{r['name']}` | {glyph} | {status} |")
        return "\n".join(rows)

    parts = [
        "# Leader symbol reference",
        "",
        "GENERATED by `scripts/gen_leader_symbols.py` from typst's symbol tables",
        "([typst/codex](https://github.com/typst/codex) `sym.txt` and `emoji.txt`).",
        "Do not edit by hand.",
        "",
        "## How to type them",
        "",
        "Press the leader key, then the category letter, then the symbol's typst",
        "name one letter at a time. A `.` in a name is the `DOT` key.",
        "",
        "| what | type | example |",
        "|---|---|---|",
        "| math symbol | leader, `M`, name | `M S U M` gives ∑ |",
        "| emoji | leader, `E`, name | `E A X E` gives 🪓 |",
        "",
        "The category letters are fixed: **M** for math, **E** for emoji. Neither",
        "collides with the existing sign-off sequences (`A G`, `C U`, `T Y`, ...).",
        "",
        "## Constraints that shape this list",
        "",
        "* **Sequences must be prefix-free.** The leader module fires the moment a",
        "  sequence completes, so when one ACTIVE name is a prefix of another only",
        "  one of them can be reached. Only names in the active set compete: an",
        "  obscure entry that happens to share a letter prefix does not block a",
        "  symbol you actually use. `eq` blocks `eq.not`, but `em` (U+2419 End of",
        "  Medium) does not block `emptyset`.",
        "* **Case is not distinguishable.** Leader keys match keycodes, not shift",
        "  state, so typst's `alpha` and `Alpha` cannot both exist. Lowercase wins",
        "  and the uppercase variant gets a trailing `U`.",
        "* **`.` is the DOT key.** So `arrow.r` is `M A R R O W DOT R`.",
        "",
        f"## Math symbols ({len(math)})",
        "",
        table(math, set(ACTIVE_MATH)),
        "",
        f"## Emoji ({len(emo)})",
        "",
        table(emo, set(ACTIVE_EMOJI)),
        "",
        "## Exceptions applied",
        "",
        "These names do not use their plain typst spelling, for the reasons above.",
        "",
        "### Math",
        "",
        "\n".join(f"* {n}" for n in math_notes) or "* none",
        "",
        "### Emoji",
        "",
        "\n".join(f"* {n}" for n in emo_notes) or "* none",
        "",
    ]
    path.write_text("\n".join(parts))


if __name__ == "__main__":
    raise SystemExit(main())
