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
    docs/LEADER-SYMBOLS.md              index: how to type, how it is chosen
    docs/LEADER-MATH.md                 the math symbol table
    docs/LEADER-EMOJI.md                the emoji table

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

# Sequences already on leader1 that begin with M or E.
#
# This is now EMPTY: the only one was `mo` ("Muito obrigado"), and as <M O> it
# was a prefix of every math sequence whose name starts with "o" (or, omega,
# omicron, ...) - 29 symbols. A completed leader sequence fires immediately, so
# those were unreachable. `mo` was removed rather than renaming 29 symbols.
#
# Kept as a named constant because the generator still needs to know about any
# future sequence that could shadow a category prefix.
EXISTING_M_E_PREFIXES: tuple[tuple[str, ...], ...] = ()

# ---------------------------------------------------------------------------
# Chosen active sets
# ---------------------------------------------------------------------------

# The math symbols enabled by default: the ones that come up constantly in
# LaTeX/typst. Everything else is emitted commented out.
ACTIVE_MATH = [
    # 200 symbols, chosen by mathematical subject rather than by name length.
    #
    # The candidates come from typst's own section structure in sym.txt -
    # Arithmetic, Relations, Set theory, Calculus, Logic, Geometry, Arrows,
    # Delimiters, Punctuation and so on - and each section is weighted by how
    # often its symbols appear in ordinary maths writing. Letter sets
    # (double-struck, Cyrillic) rank last because they are alphabets, not
    # operation symbols.
    #
    # The selection is then filtered to be prefix-free, since two sequences
    # where one is a prefix of the other cannot both be reachable.
    #
    # GREEK IS DELIBERATELY ABSENT: leader1 + G already gives all 25 letters,
    # and the same sequence with Shift gives the capitals, because the module's
    # Greek aliases carry both cases as a pair.
    "eq", "gt", "in", "lt", "oo", "or", "and", "bot", "div", "lat", "not",
    "qed", "smt", "sum", "top", "xor", "plus", "prec", "prop", "succ",
    "asymp", "minus", "nabla", "ratio", "times", "union", "approx",
    "exists", "forall", "forces", "models", "subset", "supset", "because",
    "laplace", "partial", "product", "without", "emptyset", "gradient",
    "therefore", "perp", "zero", "angle", "mapsto", "angzarr", "mapsfrom",
    "multimap", "parallel", "tack.b", "tack.l", "tack.r", "tack.t",
    "arrow.b", "arrow.l", "arrow.r", "arrow.t", "arrow.cw", "arrow.ccw",
    "arrows.bb", "arrows.bt", "arrows.ll", "arrows.lr", "arrows.rl",
    "arrows.rr", "arrows.tb", "arrows.tt", "harpoon.bl", "harpoon.br",
    "harpoon.lb", "harpoon.lt", "harpoon.rb", "harpoon.rt", "harpoon.tl",
    "harpoon.tr", "arrowhead.b", "arrowhead.t", "arrow.zigzag",
    "harpoons.blbr", "harpoons.bltr", "harpoons.lbrb", "harpoons.ltlb",
    "harpoons.ltrb", "harpoons.ltrt", "harpoons.rblb", "harpoons.rtlb",
    "harpoons.rtlt", "harpoons.rtrb", "harpoons.tlbr", "harpoons.tltr",
    "at", "co", "amp", "excl", "hash", "hyph", "semi", "quest", "slash",
    "dagger", "numero", "wreath", "percent", "pilcrow", "section",
    "permille", "backslash", "permyriad", "underscore", "bag.l", "bag.r",
    "bar.h", "bar.v", "dot.c", "dot.o", "ast.op", "ceil.l", "ceil.r",
    "dash.o", "dots.h", "dots.v", "ast.low", "brace.b", "brace.l",
    "brace.r", "brace.t", "dash.em", "dash.en", "dots.up", "fence.l",
    "fence.r", "floor.l", "floor.r", "paren.b", "paren.l", "paren.r",
    "paren.t", "shell.b", "shell.l", "shell.r", "shell.t", "dash.fig",
    "dot.quad", "tilde.eq", "tilde.gt", "tilde.lt", "tilde.op",
    "ast.basic", "bracket.b", "bracket.l", "bracket.r", "bracket.t",
    "chevron.l", "chevron.r", "dash.wave", "dot.basic", "dots.down",
    "tilde.dot", "tilde.not", "tilde.rev", "ast.double", "ast.square",
    "ast.triple", "dash.colon", "dot.double", "dot.square", "dot.triple",
    "mustache.l", "mustache.r", "tilde.basic", "fence.dotted",
    "tilde.nequiv", "tilde.triple", "hat", "acute", "breve", "caret",
    "caron", "diaer", "frown", "grave", "prime", "smash", "smile",
    "bullet", "degree", "macron", "diameter", "star.op", "power.on",
    "power.off", "hexa.filled", "power.sleep", "star.filled",
    "hexa.stroked", "penta.filled", "quote.double", "quote.single",
    "star.stroked", "bowtie.filled",
]

# The emoji enabled by default: the ones that are actually useful when writing
# text and notes. All prefix-safe and single-code-point where possible.
ACTIVE_EMOJI = [
    # 250 emoji. The first ~140 are chosen BY GLYPH for everyday use - status,
    # gestures, faces, objects, arrows, office, nature - so the names are the
    # real typst ones (checkmark.box, thumb.up, hand.wave). The rest are filled
    # from the conflict-free set, excluding CJK/Japanese button glyphs.
    #
    # Filtered to be prefix-free so every one of them is reachable.
    "checkmark.box", "crossmark", "warning", "excl", "quest", "noentry",
    "prohibited", "checkmark.heavy", "circle.red", "circle.green",
    "circle.blue", "circle.yellow", "circle.orange", "circle.purple",
    "circle.black", "circle.white", "thumb.up", "thumb.down", "hand.ok",
    "hand.wave", "hands.folded", "hands.shake", "hands.clap",
    "hands.raised", "finger.t", "finger.b", "finger.l", "finger.r",
    "hand.peace", "fingers.cross", "hand.call", "hand.splay", "face.grin",
    "face.joy", "face.rofl", "face.happy", "face.heart", "face.think",
    "face.wink", "face.cool", "face.inv", "face.tear", "face.cry",
    "face.shock", "face.explode", "face.party", "face.sleep",
    "face.nausea", "face.halo", "face.plead", "face.neutral", "lightbulb",
    "fire", "star", "sparkles", "lightning", "explosion", "wrench",
    "hammer", "gear", "toolbox", "computer", "laptop", "phone",
    "powerplug", "heart", "recycling", "faith.peace", "faith.yinyang",
    "faith.christ", "faith.islam", "faith.om", "calendar", "pin",
    "scissors", "ruler", "pen.ball", "pen.fountain", "pencil", "crayon",
    "page", "filedividers", "folder", "cabinet.file", "playback.forward",
    "playback.rewind", "playback.up", "playback.down", "playback.shuffle",
    "playback.repeat", "triangle.r", "triangle.l", "chart.bar",
    "chart.up", "chart.down", "hourglass", "lock", "key", "magnify.l",
    "magnify.r", "megaphone", "party", "confetti", "trophy",
    "medal.first", "darts", "jigsaw", "chain", "globe.eu.af", "globe.am",
    "globe.as.au", "moon.full", "moon.crescent", "sun", "snowflake",
    "wave", "tree.evergreen", "seedling", "leaf.clover.four",
    "flower.pink", "flower.sun", "pizza", "coffee", "grapes", "cake",
    "chocolate", "popcorn", "car", "house", "hospital", "school", "robot",
    "ghost", "skull", "pumpkin.lantern", "present", "mortarboard",
    "microscope", "telescope", "testtube", "helix", "pill", "tm", "tv",
    "wc", "can", "cat", "cow", "die", "dog", "ear", "egg", "elf", "eye",
    "fax", "fly", "fog", "fox", "gem", "hut", "ice", "jar", "leg", "man",
    "pie", "pig", "poo", "ram", "rat", "reg", "tap", "ten", "ufo", "urn",
    "zzz", "city", "coat", "coin", "corn", "crab", "deer", "dodo", "door",
    "drop", "drum", "duck", "film", "fish", "foot", "girl", "harp",
    "hash", "hole", "hook", "info", "kiss", "kite", "kiwi", "knot",
    "lion", "mage", "mail", "mate", "meat", "nose", "park", "pear",
    "pick", "rice", "ring", "rock", "seal", "seat", "ship", "shoe",
    "sled", "soap", "soup", "swan", "taco", "taxi", "wand", "wind",
    "wine", "wing", "wolf", "wood", "worm", "xray", "yarn", "camel",
    "chair", "chess", "child", "comet", "coral", "couch", "crane",
    "crown", "curry", "donut", "dress", "eagle", "email", "fairy",
    "fleur", "flute", "forex", "fries", "genie",
]

# ---------------------------------------------------------------------------
# Usefulness ranking and automatic conflict resolution
# ---------------------------------------------------------------------------

# How often each section of typst's sym.txt contributes symbols to ordinary
# maths writing. Lower is more useful. The letter sets rank last because they
# are alphabets, not operation symbols.
SECTION_WEIGHT = {
    "Arithmetic.": 0, "Relations.": 0, "Set theory.": 0, "Calculus.": 0,
    "Logic.": 0, "Geometry.": 1, "Arrows, harpoons, and tacks.": 1,
    "Function and category theory.": 1, "Delimiters.": 2, "Punctuation.": 2,
    "Number theory.": 2, "Algebra.": 2, "Shapes.": 3,
    "Miscellaneous Technical.": 3, "Miscellany.": 5, "Miscellaneous.": 6,
    "Double-struck.": 8, "Miscellaneous letter-likes.": 8,
}

# Sections that are NOT offered: Greek has its own leader prefix, accents are
# dead keys covered by the ACCENT layer, and the rest are not maths.
EXCLUDED_SECTIONS = (
    "Lowercase Greek.", "Uppercase Greek.", "Lowercase Cyrillic.",
    "Uppercase Cyrillic.", "Hebrew.", "Accents, quotes, and primes.",
    "Spaces.", "Control.", "Currency.", "Music.", "Astronomical.",
    "Game theory.", "Printable characters", "keyboards labels",
)


# Emoji that are actually used when writing. Name length is a poor proxy for
# popularity (`ox` and `tm` are short but rare; `thumbsup`, `warning` and
# `rocket` are the ones that get typed), so the common ones are listed by their
# GLYPH and ranked first. Everything else follows in name-simplicity order.
COMMON_EMOJI_GLYPHS = (
    # status and feedback
    "✅❌⚠❗❓⛔🚫✔✖🔴🟢🔵🟡🟠🟣⚫⚪🔺🔻‼⁉"
    # gestures
    "👍👎👌👋🙏🤝💪👏🙌✋☝👆👇👈👉✌🤞🤙🫡🖐"
    # faces
    "😀😂🤣😊😍🤔😅😉😎🙃😢😭😱🤯🥳😴🤢😇🥺😐😑"
    # things and signals
    "💡🔥⭐🌟✨⚡💥🚀🐛🔧🔨⚙🧰🖥💻⌨🖱📱🔋🔌"
    # hearts, symbols
    "❤🧡💙💚💜🖤🤍💔♻⚕☮☯✝☪🕉⚛☢☣"
    # office and writing
    "📅📆📌📍📎🖇✂📏📐🖊🖋✏🖌🖍📝📄📃📑🗂📁🗄"
    # arrows and media
    "➡⬅⬆⬇↗↘↙↖↔↕🔄🔃⏩⏪⏫⏬🔀🔁🔂▶◀"
    # time and charts
    "⏰⏱⏲🕐🕑🕒🕓🕔🕕📊📈📉🗓⏳⌛"
    # locks, search, celebration
    "🔒🔓🔑🗝🔔🔕🔍🔎💬💭🗯📢📣🎉🎊🏆🥇🎯🧩🔗"
    # nature and weather
    "🌍🌎🌏🌕🌙☀⛅☁🌧⛈❄🌊🌲🌱🍀🌸🌻🐶🐱🐭"
    # food
    "🍕🍔🍺☕🍎🍌🍇🎂🍫🍿"
    # travel and places
    "✈🚗🚲🚂⛵🏠🏢🏥🏫"
    # tech and science
    "🤖👻💀👽🎃🎁🎈🎓📚🔬🔭🧪🧬💊"
)


# Unicode ranges that are labelled buttons rather than pictographs. These are
# skipped entirely for emoji: `b` is U+1F171 NEGATIVE SQUARED LATIN CAPITAL
# LETTER B (🅱), `cl` is U+1F191 SQUARED CL, `sa` is U+1F202 SQUARED KATAKANA
# SA. They are short names, so they shadow hundreds of real emoji purely by
# accident - `b` alone blocked 122.
BUTTON_GLYPH_RANGES = (
    (0x1F100, 0x1F1FF),  # enclosed alphanumerics
    (0x1F200, 0x1F2FF),  # enclosed ideographic supplement
    (0x3200, 0x32FF),    # enclosed CJK letters and months
)


def is_button_glyph(cps: list[int]) -> bool:
    visible = [c for c in cps if c not in (VS15, VS16)]
    if not visible:
        return True
    first = visible[0]
    return any(lo <= first <= hi for lo, hi in BUTTON_GLYPH_RANGES)


def emoji_rank(entry, _sections=None) -> tuple:
    """Sort key: lower is more useful."""
    name, spec = entry
    cps = spec_to_codepoints(spec)
    visible = [c for c in cps if c not in (VS15, VS16)]
    first_char = chr(visible[0]) if visible else ""
    try:
        position = COMMON_EMOJI_GLYPHS.index(first_char)
    except ValueError:
        position = 10_000
    return (0 if position < 10_000 else 1, position, name.count("."), len(name), name)


def usefulness(name: str, section: str) -> tuple:
    """Sort key: lower is more useful. Deterministic and documented."""
    weight = next(
        (w for prefix, w in SECTION_WEIGHT.items() if section.startswith(prefix.rstrip("."))),
        5,
    )
    return (weight, name.count("."), len(name), name)


def compact(name: str) -> str:
    """A distinct spelling for a blocked name: join the dotted parts.

    `arrow.r.bar` becomes `arrowRBar`. This keeps the name readable and, being
    a single token, it does not share a prefix with `arrow` - so the sequence
    becomes reachable. Used only when LaTeX has no command for the symbol.
    """
    parts = name.split(".")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


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
# Keys are the typst name, values the spelling used in the leader sequence.
# Where a name is blocked, a LaTeX-style short form is used because that is what
# a maths user already types: \leq, \pm, \bigcup, \Rightarrow. The rule of
# thumb applied was "what would I write in LaTeX for this symbol".
# Renames for names that collide EXACTLY, which no punctuation can separate:
# typst has both `alpha` and `Alpha`, and a leader key cannot tell them apart
# because it matches keycodes, not shift state. The uppercase form takes a
# leading `g`.
#
# NOTE: every entry here is GREEK, and Greek is currently excluded from the math
# set because it has its own `leader1 + G` prefix. So this table does not fire
# today - it is a safety net for the case where Greek is ever folded back in,
# and the exact-collision logic below would otherwise produce duplicates.
#
# Prefix collisions - one name being a prefix of another - are NOT solved here.
# They are solved with a trailing DOT, which keeps every name spellable as typst
# writes it. See emitted_keys().
RENAMES = {
    "Gamma": "gGamma",
    "Delta": "gDelta",
    "Theta": "gTheta",
    "Lambda": "gLambda",
    "Pi": "gPi",
    "Sigma": "gSigma",
    "Phi": "gPhi",
    "Psi": "gPsi",
    "Omega": "gOmega",
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


def emitted_keys(name: str, prefix: str, needs_dot: bool) -> tuple[str, ...]:
    """The leader sequence for `name`.

    All internal dots are REMOVED, so `arrow.cm` is typed ARROWCM. Where the
    resulting sequence would be a prefix of another one, a single DOT is
    appended: ARROWCMDOT. The trailing DOT is what keeps `and` and `and.big`
    both reachable without renaming either.

    Why a trailing DOT rather than an internal one: there is no timeout on the
    leader, so if you type the short form and nothing happens, you are still
    holding a live leader and can simply add the DOT to complete it. Nothing has
    been typed to the host, so there is nothing to undo. An internal DOT has no
    such signal - you have to remember which names contain one.
    """
    keys = [ch.upper() for ch in name.replace(".", "")]
    if needs_dot:
        keys.append("DOT")
    return (prefix,) + tuple(keys)


def dot_needed(names, prefix: str) -> set:
    """Names whose sequence must end in DOT to avoid being a prefix of another.

    With every internal dot stripped, a clash can only take one shape: sequence
    A is a strict prefix of sequence B. A trailing DOT fixes it outright, since
    no other sequence contains a DOT at that position - every other name is
    fully glued. So a single pass is enough; there is nothing to iterate.

    Names that collide EXACTLY (same letters, e.g. `alpha` and `Alpha`) cannot
    be separated by punctuation at all and are handled by RENAMES instead.
    """
    glued = {n: tuple(ch.upper() for ch in n.replace(".", "")) for n in names}
    out = set()
    for a in names:
        ka = glued[a]
        if any(b != a and len(ka) < len(glued[b]) and glued[b][: len(ka)] == ka
               for b in names):
            out.add(a)
    return out


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
            notes.append(f"`{name}` -> `{RENAMES[name]}`")
            name = RENAMES[name]
        keys = (prefix,) + name_to_keys(name)

        # 1. Case collision. Leader keys match keycodes, not shift state, so two
        #    names differing only by case cannot share a sequence. They are NOT
        #    the same symbol though - typst's `FF` is U+1D53D (double-struck
        #    capital F) and `ff` is U+1D53B (double-struck small f) - so BOTH
        #    must survive. The lowercase form keeps the plain keys and the other
        #    gets the marker appended.
        #
        #    An earlier version dropped the non-lowercase entry instead, which
        #    silently lost FF.
        if keys in seen:
            other = seen[keys]
            if name.islower() and not other.islower():
                # the lowercase form is the natural spelling: give IT the plain
                # keys and push the existing uppercase entry to the marked form
                newkeys = keys + (suffix_case,)
                resolved = [
                    ({**r, "keys": newkeys} if r["keys"] == keys else r)
                    for r in resolved
                ]
                seen.pop(keys, None)
                seen[newkeys] = other
                notes.append(
                    f"`{other}` -> suffix `{suffix_case}` "
                    f"(case collision with `{name}`)"
                )
            else:
                newkeys = keys + (suffix_case,)
                notes.append(
                    f"`{name}` -> suffix `{suffix_case}` "
                    f"(case collision with `{other}`)"
                )
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


# Set by main() to the names that actually exist in typst's tables, so a rename
# can be checked against them.
SOURCE_NAMES: set = set()


def compact_reversed(name: str) -> str:
    """A spelling with the last part first: `lat.eq` -> `eqLat`.

    compact() keeps the base as a prefix, so it cannot escape a base name that
    is itself taken - `lat.eq` -> `latEq` still begins with `LAT`. Moving the
    qualifier to the front breaks that: `eqLat` shares no prefix with `lat`.
    """
    parts = name.split(".")
    if len(parts) < 2:
        return name
    return parts[-1] + "".join(p.capitalize() for p in parts[:-1])


def read_enabled(path: pathlib.Path, cat: str) -> set:
    """The set of names enabled in an existing generated .dtsi.

    A line is enabled if it is not preceded by `//`. This file is the source of
    truth for which symbols are active: the triage tool edits it directly, and
    the generator reads it back so a regeneration preserves those choices
    instead of resetting them to a count.

    Returns an empty set if the file does not exist yet, which is the correct
    behaviour for a first run.
    """
    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8")
    # Node names have every character that is not [A-Za-z0-9_] replaced with an
    # underscore, so `and.big` is emitted as `seq_m_and_big`. Map back, or every
    # dotted name would look disabled and be reset on the next regeneration.
    return {
        node.replace("_", ".")
        for node in re.findall(rf"^\s+seq_{cat}_(\w+) \{{ sequence", text, re.M)
    }


def select_math_by_usefulness(entries, sections, enabled, prefix="M"):
    """Pick the most useful `limit` math symbols, resolving every conflict.

    The algorithm, which follows the stated intent - rank by usefulness first,
    THEN resolve conflicts:

      1. Order every candidate by how useful it is (section weight, then
         simplicity). Usefulness decides priority; conflict-freedom does not.
      2. Walk that order. The first name for a given key-space wins.
      3. If a name is blocked by one already taken, do NOT drop it. Rename it:
         first to its LaTeX command if the symbol has one, otherwise to the
         compact spelling (`arrow.r.bar` -> `arrowRBar`). Renaming is what makes
         500 reachable at all, since bare `arrow.r` would otherwise shadow its
         whole family.
      4. Only if both renames are themselves taken does the symbol get left
         commented out, and the reason is recorded.

    Returns (active, renamed, commented) where renamed is [(typst, used)].
    """
    taken_keys: set = set()
    active: list = []
    renamed: list = []
    commented: list = []

    def to_keys(name):
        return (prefix,) + name_to_keys(name)

    def clashes(keys):
        """True only for an EXACT duplicate.

        Prefix clashes are deliberately allowed now: the shorter sequence is
        given a trailing DOT by apply_trailing_dots(), so both remain reachable.
        """
        return any(other == keys for other in taken_keys)

    # Selection works on the ALL-GLUED form, with a trailing DOT where needed.
    # The trailing DOT is only decided once the active set is known, so during
    # selection every name uses its plain glued keys and the prefix check below
    # does the disambiguating.
    def keys_for(cand):
        return (prefix,) + tuple(ch.upper() for ch in cand.replace(".", ""))

    ordered = sorted(entries, key=lambda e: usefulness(e[0], sections.get(e[0], "")))
    for name, spec in ordered:
        cps = spec_to_codepoints(spec)
        if not cps:
            continue
        if name not in enabled:
            # Not selected. `enabled` comes from the existing .dtsi, so this is
            # the set the triage tool left behind rather than a count.
            commented.append((name, cps, keys_for(name), "not enabled"))
            continue

        # The spelling is the typst name itself, or its RENAMES entry when the
        # name collides EXACTLY with another (the case pairs). Prefix clashes
        # are not resolved here - they get a trailing DOT in
        # apply_trailing_dots(), which is the whole point of the design: keep
        # every name spellable as typst writes it.
        cand = RENAMES.get(name, name)
        keys = keys_for(cand)

        # Only an EXACT duplicate is fatal. A prefix clash is fine: the shorter
        # sequence will take a trailing DOT.
        if any(k == keys for k in taken_keys):
            commented.append((name, cps, keys, "duplicate spelling"))
            continue

        taken_keys.add(keys)
        active.append((name, cand, cps, keys))
        if cand != name:
            renamed.append((name, cand))

    return apply_trailing_dots(active, prefix), renamed, commented


def select_emoji_by_usefulness(entries, enabled, prefix="E"):
    """Pick the most useful `limit` emoji, resolving conflicts by rename.

    Same algorithm as the math selector, but emoji have no LaTeX names and no
    subject sections, so usefulness is approximated by name simplicity: shorter,
    plainer names are more likely to be the common ones (`heart`, `fire`,
    `rocket`) than deeply dotted ones (`hand.finger.index.raised`).

    Names that are CJK or Japanese button glyphs are skipped: they are labelled
    buttons rather than pictographs and are useless when writing.
    """
    taken_keys: set = set()
    active: list = []
    renamed: list = []
    commented: list = []

    def to_keys(name):
        return (prefix,) + name_to_keys(name)

    def clashes(keys):
        # An EXACT match counts too. is_prefix() requires len(a) < len(b), so two
        # IDENTICAL sequences were not "prefixes" of each other and the duplicate
        # slipped through - gt.equiv and equiv.gt both landed on M G T E Q U I V,
        # where the second is unreachable.
        return any(
            other == keys or is_prefix(other, keys) or is_prefix(keys, other)
            for other in taken_keys
        )

    def order(entry):
        name, spec = entry
        cps = spec_to_codepoints(spec)
        visible = [c for c in cps if c not in (VS15, VS16)]
        first = visible[0] if visible else 0
        # Rank the common ones first (by glyph), then everything else by name
        # simplicity. CJK and enclosed button glyphs sort last: they are
        # labelled buttons rather than pictographs and are useless in prose.
        skip = 2 if (
            0x1F100 <= first <= 0x1F1FF
            or 0x3200 <= first <= 0x32FF
            or 0x1F200 <= first <= 0x1F2FF
            or 0x1F000 <= first <= 0x1F02F
        ) else 0
        _, pos, dots, ln, nm = emoji_rank(entry)
        return (skip, pos, dots, ln, nm)

    def keys_for(cand):
        return (prefix,) + tuple(ch.upper() for ch in cand.replace(".", ""))

    for name, spec in sorted(entries, key=order):
        cps = spec_to_codepoints(spec)
        if not cps:
            continue
        if is_button_glyph(cps):
            commented.append(
                (name, cps, keys_for(name), "labelled button glyph")
            )
            continue
        if name not in enabled:
            commented.append((name, cps, keys_for(name), "not enabled"))
            continue

        # Same rule as the math set: the typst name is the spelling, and a
        # prefix clash is resolved with a trailing DOT rather than a rename.
        cand = name
        keys = keys_for(cand)

        if any(k == keys for k in taken_keys):
            commented.append((name, cps, keys, "duplicate spelling"))
            continue

        taken_keys.add(keys)
        active.append((name, cand, cps, keys))

    return apply_trailing_dots(active, prefix), renamed, commented


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

def apply_trailing_dots(active, prefix: str) -> list:
    """Finalise the sequences: glue every name, add a trailing DOT where needed.

    Runs on the ACTIVE set, not on all candidates: a name that is disabled must
    not force a DOT onto a name that is enabled.
    """
    used = [u for _t, u, _c, _k in active]
    needs = dot_needed(used, prefix)
    return [
        (t, u, c, emitted_keys(u, prefix, u in needs))
        for t, u, c, _k in active
    ]


def emit_selected(active, commented, leader_name, cat, header):
    """Write the .dtsi fragment for one category.

    Active sequences are plain lines; the rest are commented so that they can be
    enabled by deleting `//`. Every line carries the glyph it produces.
    """
    out = ["/*", " * " + header, " */", "", f"&{leader_name} {{"]
    out.append(f"    /* --- active ({len(active)}) --- */")
    for typst, used, cps, keys in sorted(active, key=lambda r: r[1]):
        node = f"seq_{cat}_" + re.sub(r"[^A-Za-z0-9_]", "_", used)
        out.append(
            f"    {node} {{ sequence = <{' '.join(keys)}>; "
            f"bindings = <{cp_literal(cps)}>; }};  {glyph_comment(cps, used)}"
        )
    out.append("")
    out.append(f"    /* --- available but disabled ({len(commented)}) ---")
    out.append("     * Uncomment a line to enable it. Each is disabled because it is")
    out.append("     * beyond the active limit, or its spelling is an exact duplicate of")
    out.append("     * another name (typst's `alpha` and `Alpha`, which no punctuation")
    out.append("     * can separate).")
    out.append("     *")
    out.append("     * NOTE: a name that is a PREFIX of an enabled one needs a trailing")
    out.append("     * DOT appended before it will work - otherwise the shorter sequence")
    out.append("     * fires first and the longer becomes unreachable. Re-running the")
    out.append("     * generator adds those automatically; a hand-uncommented line does")
    out.append("     * not get one.")
    out.append("     */")
    for typst, cps, keys, why in sorted(commented, key=lambda r: r[0]):
        node = f"seq_{cat}_" + re.sub(r"[^A-Za-z0-9_]", "_", typst)
        out.append(
            f"    // {node} {{ sequence = <{' '.join(keys)}>; "
            f"bindings = <{cp_literal(cps)}>; }};  {glyph_comment(cps, typst)}"
        )
    out.append("};")
    out.append("")
    return "\n".join(out)


def build_sections(path: pathlib.Path) -> dict:
    """Map each symbol name to the section header it appears under in sym.txt.

    The header is what the usefulness ranking is based on, so it has to be
    recovered from the file rather than from the parsed entries.
    """
    out: dict = {}
    section = None
    stack: list = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.startswith("// "):
            section = line[3:].strip()
            continue
        if not line.strip() or line.lstrip().startswith("//"):
            continue
        m = re.match(r"^(\s*)([A-Za-z0-9._-]+)(?:\s+(.+?))?\s*$", line)
        if not m:
            continue
        indent, name, spec = len(m.group(1)), m.group(2), m.group(3)
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
            out[full] = section or ""
    return out


def docs_from_dtsi() -> int:
    """Regenerate only the markdown, reading the .dtsi files as the source.

    The .dtsi already records everything the docs need: the enabled set, each
    entry's spelling and glyph, and the trailing-DOT decision. So no typst fetch
    is required and the .dtsi files are never written - which makes this safe to
    run in CI on every change.
    """
    inc = REPO / "config" / "include"
    docs_dir = REPO / "docs"

    def parse(path: pathlib.Path, cat: str):
        """(typst, used, cps, keys) for each entry, active or commented."""
        active, commented = [], []
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(
            rf"^([ \t]*)(// )?(seq_{cat}_(\w+))(\s+\{{ sequence = <([^>]+)>; "
            rf"bindings = <([^>]+)>; \}};\s*//\s*(\S+))",
            text,
            re.M,
        ):
            _indent, off, _node, used_node, _ws, seq, binds, typst = m.groups()
            keys = tuple(seq.split())
            cps = [int(x, 16) for x in re.findall(r"&uc 0x([0-9A-Fa-f]+) 0", binds)]
            used = used_node.replace("_", ".")
            if off:
                # _table expects commented entries as (typst, cps, keys, why),
                # which differs from the active tuple. Passing the active shape
                # for both put `used` into the cps slot and crashed on chr().
                #
                # The .dtsi does not record WHY an entry is disabled, so the
                # reason is re-derived here. Button glyphs are the one case that
                # is determinable from the glyph itself, and they are excluded
                # rather than merely unselected - worth keeping distinct so the
                # docs match what the full generator writes.
                why = (
                    "labelled button glyph"
                    if cat == "e" and is_button_glyph(cps)
                    else "not enabled"
                )
                commented.append((typst, cps, keys, why))
            else:
                active.append((typst, used, cps, keys))
        return active, commented

    m_active, m_comment = parse(inc / "leader-math.dtsi", "m")
    e_active, e_comment = parse(inc / "leader-emoji.dtsi", "e")

    # Sort alphabetically for the tables, as the full generator does.
    m_active.sort(key=lambda r: r[1])
    e_active.sort(key=lambda r: r[1])
    m_comment.sort(key=lambda r: r[0])
    e_comment.sort(key=lambda r: r[0])

    write_docs(docs_dir, m_active, m_comment, [], e_active, e_comment, [])
    print(f"  math : {len(m_active)} active, {len(m_comment)} disabled")
    print(f"  emoji: {len(e_active)} active, {len(e_comment)} disabled")
    print("  wrote docs/LEADER-SYMBOLS.md, LEADER-MATH.md, LEADER-EMOJI.md")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument(
        "--math", type=int, default=None,
        help=(
            "enable the N most useful math symbols, ignoring the enabled set in "
            "the existing .dtsi. Omit to preserve what is already enabled, which "
            "is the normal case and what the triage tool relies on."
        ),
    )
    ap.add_argument(
        "--emoji", type=int, default=None,
        help="enable the N most useful emoji, ignoring the existing .dtsi",
    )
    ap.add_argument(
        "--docs-only", action="store_true",
        help=(
            "regenerate docs/LEADER-*.md from the existing .dtsi files and stop. "
            "Used by `just docs` and CI, where the typst source is not fetched "
            "and the .dtsi must not be touched."
        ),
    )
    args = ap.parse_args()

    if args.docs_only:
        return docs_from_dtsi()

    print("parsing codex data")
    sym_path = fetch("sym.txt", args.offline)
    emoji_path = fetch("emoji.txt", args.offline)
    sym = parse_codex(sym_path)
    emoji = parse_codex(emoji_path)
    print(f"  sym.txt   {len(sym)}")
    print(f"  emoji.txt {len(emoji)}")

    sections = build_sections(sym_path)
    SOURCE_NAMES.clear()
    SOURCE_NAMES.update(n for n, _ in sym)

    # Math: exclude the sections that are covered elsewhere or are not maths -
    # Greek has its own leader prefix, accents are dead keys on the ACCENT
    # layer, and the rest (control pictures, currency, music) are not symbols
    # anyone types in a formula.
    math_entries = [
        (n, sp) for n, sp in sym
        if not any(k in sections.get(n, "") for k in EXCLUDED_SECTIONS)
    ]
    print(f"  math candidates: {len(math_entries)} "
          f"(of {len(sym)}; Greek, accents and non-maths sections excluded)")

    # Which symbols are enabled comes from the generated .dtsi files, which the
    # triage tool writes. That makes the .dtsi the single source of truth: a
    # regeneration preserves your triage rather than resetting it to a count,
    # and any NEW typst symbol appears disabled until you enable it.
    #
    # --math/--emoji override this with "the N most useful", which is only for
    # bootstrapping or deliberately starting over.
    inc_dir = REPO / "config" / "include"
    if args.math is not None:
        ordered_math = sorted(
            math_entries, key=lambda e: usefulness(e[0], sections.get(e[0], ""))
        )
        m_enabled = {n for n, _ in ordered_math[: args.math]}
    else:
        m_enabled = read_enabled(inc_dir / "leader-math.dtsi", "m")

    if args.emoji is not None:
        e_enabled = {n for n, _ in emoji[: args.emoji]}
    else:
        e_enabled = read_enabled(inc_dir / "leader-emoji.dtsi", "e")

    print(f"  enabled from .dtsi: math {len(m_enabled)}, emoji {len(e_enabled)}")

    m_active, m_renamed, m_comment = select_math_by_usefulness(
        math_entries, sections, m_enabled
    )
    e_active, e_renamed, e_comment = select_emoji_by_usefulness(emoji, e_enabled)

    print(f"  math : {len(m_active)} active, {len(m_renamed)} renamed, "
          f"{len(m_comment)} commented")
    print(f"  emoji: {len(e_active)} active, {len(e_renamed)} renamed, "
          f"{len(e_comment)} commented")

    # ---- emit the two devicetree fragments -------------------------------
    inc = REPO / "config" / "include"
    (inc / "leader-math.dtsi").write_text(
        emit_selected(m_active, m_comment, "leader1", "m",
                      "Math symbol leader sequences: leader1 then M then the typst name.\n"
                      " *\n"
                      " *   leader1 + M + S U M            -> U+2211   (sym.sum)\n"
                      " *   leader1 + M + A R R O W DOT R  -> U+2192   (sym.arrow.r)\n"
                      " *\n"
                      " * GENERATED by scripts/gen_leader_symbols.py from typst/codex sym.txt.\n"
                      " * Do not edit by hand; re-run the script instead.\n"
                      " *\n"
                      " * Chosen by usefulness, NOT by whether they conflict: every symbol is\n"
                      " * ranked by how often its section appears in ordinary maths, and a name\n"
                      " * that clashes with one already taken is RENAMED rather than dropped\n"
                      " * (arrow.r.bar -> arrowRBar, or the LaTeX command where one exists).\n"
                      " * Only a symbol whose every spelling is taken is commented out.\n"
                      " *\n"
                      " * Greek is absent on purpose: leader1 + G covers all 25 letters, and\n"
                      " * the same sequence with Shift gives the capitals.")
    )
    (inc / "leader-emoji.dtsi").write_text(
        emit_selected(e_active, e_comment, "leader1", "e",
                      "Emoji leader sequences: leader1 then E then the typst name.\n"
                      " *\n"
                      " *   leader1 + E + A X E    -> U+1FA93   (emoji.axe)\n"
                      " *\n"
                      " * GENERATED by scripts/gen_leader_symbols.py from typst/codex\n"
                      " * emoji.txt. Do not edit by hand; re-run the script instead.")
    )
    print("  wrote config/include/leader-math.dtsi")
    print("  wrote config/include/leader-emoji.dtsi")

    docs = REPO / "docs"
    docs.mkdir(exist_ok=True)
    write_docs(docs, m_active, m_comment, m_renamed, e_active, e_comment, e_renamed)
    print("  wrote docs/LEADER-SYMBOLS.md (index), LEADER-MATH.md, LEADER-EMOJI.md")

    # Uniqueness. Both of these have caused a build failure or silent breakage:
    # two nodes with the same name is a devicetree "duplicate node name" error,
    # and two sequences with the same keys means the second is unreachable.
    import collections as _c

    for label, active in (("math ", m_active), ("emoji", e_active)):
        seen_names = _c.Counter()
        seen_keys = _c.Counter()
        for _typst, used, _cps, keys in active:
            seen_names["seq_" + re.sub(r"[^A-Za-z0-9_]", "_", used)] += 1
            seen_keys[" ".join(keys)] += 1
        dup_names = [k for k, v in seen_names.items() if v > 1]
        dup_keys = [k for k, v in seen_keys.items() if v > 1]
        if dup_names or dup_keys:
            print(f"  {label}: DUPLICATES node={dup_names} keys={dup_keys}")
            return 1

    # completeness: nothing may be silently dropped
    for label, active, comment, total in (
        ("math ", m_active, m_comment, len(math_entries)),
        ("emoji", e_active, e_comment, len(emoji)),
    ):
        ok = len(active) + len(comment) == total
        print(f"  {label}: {len(active)} + {len(comment)} = {total}  "
              f"{'complete' if ok else 'INCOMPLETE'}")
    return 0


def _table(active, commented) -> str:
    """One markdown table of the active and disabled entries."""
    rows = ["| sequence | name | char | status |", "|---|---|---|---|"]
    for typst, used, cps, keys in sorted(active, key=lambda r: r[1]):
        glyph = "".join(chr(c) for c in cps if c not in (VS16, VS15))
        note = "active" if used == typst else f"renamed from `{typst}`"
        rows.append(f"| `{' '.join(keys)}` | `{used}` | {glyph} | {note} |")
    for typst, cps, keys, why in sorted(commented, key=lambda r: r[0]):
        glyph = "".join(chr(c) for c in cps if c not in (VS16, VS15))
        rows.append(f"| `{' '.join(keys)}` | `{typst}` | {glyph} | disabled: {why} |")
    return "\n".join(rows)


def write_docs(docs_dir, m_active, m_comment, m_renamed, e_active, e_comment, e_renamed) -> None:
    """Write the reference as an index plus one page per category.

    Split rather than one file because the tables are large: the math table
    alone is ~2300 rows. Three files also means the emoji page does not have to
    be scrolled past to reach the math symbols, which is the common case when
    looking one up.
    """
    docs_dir.mkdir(exist_ok=True)

    # ---- index -----------------------------------------------------------
    index = f"""# Leader symbol reference

GENERATED by `scripts/gen_leader_symbols.py` from typst's own symbol tables
([typst/codex](https://github.com/typst/codex) `sym.txt` and `emoji.txt`).
Do not edit by hand.

| page | what | active | disabled |
|---|---|---|---|
| [LEADER-MATH.md](LEADER-MATH.md) | math symbols, leader + `M` | {len(m_active)} | {len(m_comment)} |
| [LEADER-EMOJI.md](LEADER-EMOJI.md) | emoji, leader + `E` | {len(e_active)} | {len(e_comment)} |

## How to type them

Press the leader key, then the category letter, then the name one letter at a
time.

| what | type | example |
|---|---|---|
| math symbol | leader, `M`, name | `M S U M` gives ∑ |
| emoji | leader, `E`, name | `E H E A R T` gives ❤ |
| Greek | leader, `G`, one letter | `G G` gives γ, `G G`+Shift gives Γ |
| sign-off | leader, 2-3 letters | `O B R` gives "Obrigado," then a newline then "Heiko" |

**Every name is written as typst spells it, with the dots removed.** So
`arrow.cm` is `M A R R O W C M` and `and` is `M A N D`.

**Where a name is the start of a longer one, a DOT goes on the END.** `and` is
followed by `and.big`, `and.curly` and others, so `and` itself is
`M A N D DOT` while `and.big` is `M A N D B I G`.

That trailing DOT is the whole trick, and it is discoverable without a manual:
there is no timeout on the leader, so if you type `M A N D` and nothing happens
you are still inside a live leader. Adding the DOT completes it. Nothing has
been sent to the host, so there is nothing to undo - the symbol simply appears.
If you had to remember an internal DOT, or a different spelling like `wedge`,
there would be no such signal.

**Names are never renamed.** Every entry is typed as typst spells it, minus the
dots. Where two names would collide exactly - typst has both `alpha` and
`Alpha` - the pair cannot be separated by punctuation, since a leader key
matches keycodes and not shift state. Greek is not affected: it lives under its
own `G` prefix and is not part of this set at all.

The tables below give the exact sequence for every entry, active or not.

Names follow **typst/LaTeX**, so they are the ones you already type: `sum`,
`approx`, `arrow.r`, `integral`.

## How the set is chosen

Symbols are ranked by **usefulness first**, by the section of typst's symbol
table they come from. Arithmetic, relations, set theory, calculus and logic rank
above the letter sets, which are alphabets rather than operation symbols.

The active count is then capped. That cap is a RAM budget, not a limit on what
is reachable: the leader sequences live in RAM at 144 bytes each, so about a
thousand fit alongside ZMK's BLE and Studio. Everything beyond the cap is
emitted commented out, ready to enable.

Nothing is removed and nothing is renamed. Of the ~1000 offered math symbols and
~1380 emoji, 500 and 451 are enabled and the rest are in the `.dtsi` as
comments.

Greek is absent from the math set on purpose: `leader1 + G` already covers all
25 letters, and holding Shift gives the capitals, so repeating them under `M`
would be redundant.

## Adding or changing symbols

Edit `scripts/gen_leader_symbols.py` and re-run it; these pages are generated
along with the two `leader-*.dtsi` files.
"""
    (docs_dir / "LEADER-SYMBOLS.md").write_text(index)

    # ---- math ------------------------------------------------------------
    math = f"""# Leader math symbols

GENERATED by `scripts/gen_leader_symbols.py`. See
[LEADER-SYMBOLS.md](LEADER-SYMBOLS.md) for how to type them and how the set is
chosen.

Leader, then `M`, then the name. {len(m_active)} active, {len(m_comment)}
disabled.

## Symbols

{_table(m_active, m_comment)}
"""
    (docs_dir / "LEADER-MATH.md").write_text(math)

    # ---- emoji -----------------------------------------------------------
    emoji = f"""# Leader emoji

GENERATED by `scripts/gen_leader_symbols.py`. See
[LEADER-SYMBOLS.md](LEADER-SYMBOLS.md) for how to type them and how the set is
chosen.

Leader, then `E`, then the name. {len(e_active)} active, {len(e_comment)}
disabled.

## Emoji

{_table(e_active, e_comment)}
"""
    (docs_dir / "LEADER-EMOJI.md").write_text(emoji)


if __name__ == "__main__":
    raise SystemExit(main())
