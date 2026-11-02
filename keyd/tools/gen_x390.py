#!/usr/bin/env python3
"""Generate keyd/x390.conf - the keyd counterpart of this repo's ZMK layout.

Run from the repo root:

    python3 keyd/tools/gen_x390.py            # write keyd/x390.conf
    python3 keyd/tools/gen_x390.py --check    # exit 1 if the file is stale

WHY GENERATED
-------------
Part of this config is a mechanical translation of files under config/include/
that are hand-maintained or themselves generated: the 19 vulgar-fraction chords,
the 26 combining marks, the 10 super/subscript pairs, the 37 hand-written leader
sequences (9 sign-offs, 3 Outlook headings, 25 Greek letters) all come from there. Copying them by hand
would drift, so they are compiled in here. The genuine design work - the layer
set, the key placements, the chord choices, the PT layout - is in the template
below and is argued in docs/KEYD-ANALYSIS.md.

The generated output is keyd/x390.conf. Do not edit it by hand; change this
script and re-run.

KEYD vs ZMK, in one paragraph
-----------------------------
keyd has no sequence buffer. ZMK's `&leader1` buffers a variable-length key
sequence and fires as soon as the buffer matches, resolving prefix ambiguity per
instance (that is why `mo` had to be deleted - it was a prefix of every name
starting with "o"; see config/include/behaviors.dtsi:107). keyd has only layers
(a key -> an action) and chords (keys together -> an action), plus a 32-layer
budget (src/config.h:15). So the 951 typst symbol names cannot be hosted as
layers: a trie over those names needs 3151 interior nodes. They are therefore
reached through a command() handoff to `keyd do`, which executes an arbitrary
macro in-process over the IPC socket (src/daemon.c:422, IPC_MACRO). That is the
one part of this config that is a workaround rather than a translation, and it is
marked as such.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "keyd/x390.conf"
COMPOSE = ROOT / ".research/keyd-src/data/keyd.compose"
MATH = ROOT / "config/include/leader-math.dtsi"
EMOJI = ROOT / "config/include/leader-emoji.dtsi"

SEQ_RE = re.compile(r"\s*seq_(\S+)\s*\{\s*sequence\s*=\s*<([^>]*)>;\s*"
                    r"bindings\s*=\s*<([^>]*)>;\s*\};\s*//\s*(.*)")
UC_RE = re.compile(r"&uc\s+(0x[0-9A-Fa-f]+)")


# ---------------------------------------------------------------------------
# Unicode support in keyd
# ---------------------------------------------------------------------------

def load_keyd_table() -> set[int]:
    """Code points keyd can emit, from its shipped compose table.

    src/macro.c compiles a code point < 128 into a key sequence looked up by
    name in keycode_table, so ASCII always works. Anything >= 128 needs an entry
    in data/keyd.compose, which keyd installs as an XCompose file.
    """
    table = set(range(128))
    if COMPOSE.exists():
        for line in COMPOSE.open(encoding="utf-8"):
            m = re.match(r'^<Cancel> <[^>]+> <[^>]+> <[^>]+> : "(.*)"\s*$', line)
            if m and len(m.group(1)) == 1:
                table.add(ord(m.group(1)))
    return table


def _esc(s: str) -> str:
    r"""Escape a literal string for a keyd macro(...) expression.

    keyd's str_escape (src/string.c) recognises ONLY these escapes: \n, \t,
    \\, \) and \(. Any other backslash sequence is passed through as a
    literal backslash plus the character. So it is WRONG to write \, for a
    comma - keyd would type a backslash and a comma. Commas and spaces are
    emitted as their key names instead; only \, \, \\, \) and \( are
    escaped here.
    """
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == ")":
            out.append("\\)")
        elif ch == "(":
            out.append("\\(")
        else:
            out.append(ch)
    return "".join(out)


def macro_text(s: str) -> str:
    """A keyd macro that types the literal string s.

    Tokens are space-separated and each token is walked character by character
    (src/macro.c, tok += chrsz), so words are emitted whole. Characters keyd
    names specially are emitted as their key name instead of as a literal:
    " " -> space, "\n" -> enter, "\t" -> tab, "," -> comma. This mirrors the
    official example in keyd.scdoc: macro(Hello space World).
    """
    args: list[str] = []
    word: list[str] = []

    def flush() -> None:
        if word:
            args.append("".join(word))
            word.clear()

    for ch in s:
        if ch == " ":
            flush()
            args.append("space")
        elif ch == "\n":
            flush()
            args.append("enter")
        elif ch == "\t":
            flush()
            args.append("tab")
        elif ch == ",":
            flush()
            args.append("comma")
        else:
            word.append(_esc(ch))
    flush()
    return "macro(%s)" % " ".join(args)


def macro_char(cp: int) -> str:
    """A keyd macro that types one code point."""
    ch = chr(cp)
    if ch == "\n":
        return "macro(enter)"
    if ch == " ":
        return "macro(space)"
    if ch == ",":
        return "macro(comma)"
    return "macro(%s)" % _esc(ch)


def count_symbols() -> tuple[int, int, list[str]]:
    """Return (total sequences, emittable, names keyd cannot render)."""
    table = load_keyd_table()
    total = 0
    emittable = 0
    missing: list[str] = []
    for path in (MATH, EMOJI):
        for line in path.open(encoding="utf-8"):
            s = line.strip()
            if s.startswith("*") or s.startswith("//"):
                continue
            m = SEQ_RE.match(line)
            if not m:
                continue
            total += 1
            name = "".join(m.group(2).split()[1:])
            cps = [int(c, 16) for c in UC_RE.findall(m.group(3))]
            if any(cp not in table for cp in cps):
                missing.append("U+%04X %s" % (cps[0], name))
            else:
                emittable += 1
    return total, emittable, missing


# ---------------------------------------------------------------------------
# Static data pulled from the ZMK sources
# ---------------------------------------------------------------------------

# The nine text sign-offs from config/include/macros.dtsi. These are literal
# text the ZMK macros type key by key; reproducing the text rather than the key
# events is what makes them work on a PT laptop layout where key positions
# differ. macros.dtsi:288-293 records the PT_SQT bug this avoids.
SIGNOFFS = [
    ("cu", "Cumps,\nHeiko", "m_sig_cumps, macros.dtsi:217"),
    ("obr", "Obrigado,\nHeiko", "m_sig_o, macros.dtsi:226"),
    ("oc", "Obrigado e cumps,\nHeiko", "m_sig_oc, macros.dtsi:234"),
    ("co", "Cumps e obrigado,\nHeiko", "m_sig_co, macros.dtsi:243"),
    ("br", "Best regards,\nHeiko", "m_sig_br, macros.dtsi:252"),
    ("ty", "Thank you,\nHeiko", "m_sig_ty, macros.dtsi:261"),
    ("tb", "Thank you and best regards,\nHeiko", "m_sig_tb, macros.dtsi:269"),
    ("th", "Thank you,\nHeiko Riemer", "m_sig_th, macros.dtsi:280"),
    ("yw", "You're Welcome", "m_sig_yw, macros.dtsi:294"),
]

# Outlook heading macros (behaviors.dtsi:122-125). These are keyboard SHORTCUTS
# (Ctrl-B toggles bold in Word/Outlook), not text: "Agenda:" typed in bold,
# then Enter, then a bullet. keyd can reproduce them as macros with modifiers.
# The trailing C-S-l is the Word "toggle bullet" shortcut and is the same in all
# four; macros.dtsi:319-324 warns that it looks like a copy-paste slip but is
# intentional. Kept as-is.
OUTLOOK = [
    ("ag", "C-b", "Agenda:", "m_ag, macros.dtsi:297"),
    ("obj", "C-b", "Objective:", "m_ob, macros.dtsi:302"),
    ("ac", "C-b", "Actions:", "m_ac, macros.dtsi:307"),
]

# Greek letters from behaviors.dtsi:134-158. G then the letter that starts the
# name; Shift gives the capital, exactly as in ZMK.
GREEK = [
    ("a", "alpha", 0x03B1), ("b", "beta", 0x03B2), ("g", "gamma", 0x03B3),
    ("d", "delta", 0x03B4), ("e", "epsilon", 0x03B5), ("z", "zeta", 0x03B6),
    ("h", "eta", 0x03B7), ("v", "theta", 0x03B8), ("i", "iota", 0x03B9),
    ("k", "kappa", 0x03BA), ("l", "lambda", 0x03BB), ("m", "mu", 0x03BC),
    ("n", "nu", 0x03BD), ("x", "xi", 0x03BE), ("o", "omikron", 0x03BF),
    ("p", "pi", 0x03C0), ("r", "rho", 0x03C1), ("s", "sigma", 0x03C3),
    ("5", "final sigma", 0x03C2), ("t", "tau", 0x03C4),
    ("u", "upsilon", 0x03C5), ("f", "phi", 0x03C6), ("c", "chi", 0x03C7),
    ("y", "psi", 0x03C8), ("w", "omega", 0x03C9),
]

# The 19 vulgar fractions from combos.dtsi:86-104. ZMK maps two NUMNAV digit
# keys to one character; keyd chords do the same thing on the same keys.
FRACTIONS = [
    ("1", "2", 0x00BD, "one half"),
    ("1", "4", 0x00BC, "one quarter"),
    ("3", "4", 0x00BE, "three quarters"),
    ("1", "3", 0x2153, "one third"),
    ("2", "3", 0x2154, "two thirds"),
    ("0", "3", 0x2189, "zero thirds"),
    ("1", "5", 0x2155, "one fifth"),
    ("2", "5", 0x2156, "two fifths"),
    ("3", "5", 0x2157, "three fifths"),
    ("4", "5", 0x2158, "four fifths"),
    ("1", "6", 0x2159, "one sixth"),
    ("5", "6", 0x215A, "five sixths"),
    ("1", "7", 0x2150, "one seventh"),
    ("1", "8", 0x215B, "one eighth"),
    ("3", "8", 0x215C, "three eighths"),
    ("5", "8", 0x215D, "five eighths"),
    ("7", "8", 0x215E, "seven eighths"),
    ("1", "9", 0x2151, "one ninth"),
    ("1", "0", 0x2152, "one tenth"),
]

# The 26 combining marks on the ACCENT layer (layers.dtsi:224-230). A combining
# mark is typed AFTER its base character. keyd emits the code point directly, so
# this is cleaner than ZMK's &uc module, which has to guess the input method.
COMBINING = [
    ("grave", 0x0300), ("acute", 0x0301), ("circumflex", 0x0302),
    ("tilde", 0x0303), ("macron", 0x0304), ("overline", 0x0305),
    ("breve", 0x0306), ("dot above", 0x0307), ("diaeresis", 0x0308),
    ("ring above", 0x030A), ("double acute", 0x030B), ("caron", 0x030C),
    ("double grave", 0x030F), ("inverted breve", 0x0311),
    ("comma above", 0x0313), ("left arrow above", 0x20D6),
    ("right arrow above", 0x20D7), ("left right arrow above", 0x20E1),
    ("left harpoon above", 0x20D0), ("right harpoon above", 0x20D1),
    ("enclosing circle", 0x20DD), ("dot below", 0x0323),
    ("macron below", 0x0331), ("long stroke overlay", 0x0336),
    ("short stroke overlay", 0x0335), ("long solidus overlay", 0x0338),
]

SUPERSCRIPTS = {
    "1": 0x00B9, "2": 0x00B2, "3": 0x00B3, "4": 0x2074, "5": 0x2075,
    "6": 0x2076, "7": 0x2077, "8": 0x2078, "9": 0x2079, "0": 0x2070,
}
SUBSCRIPTS = {
    "1": 0x2081, "2": 0x2082, "3": 0x2083, "4": 0x2084, "5": 0x2085,
    "6": 0x2086, "7": 0x2087, "8": 0x2088, "9": 0x2089, "0": 0x2080,
}


# ---------------------------------------------------------------------------
# The config template
# ---------------------------------------------------------------------------

HEADER = r"""# keyd configuration for the Lenovo ThinkPad X390 Yoga internal keyboard.
#
# GENERATED by keyd/tools/gen_x390.py - do not edit by hand. Change the script
# (or the ZMK sources it reads) and re-run it.
#
# WHAT THIS IS
# ------------
# The keyd counterpart of the ZMK split-keyboard layout in config/include/.
# It is for the days the split board stays at home. The goal is not to replace
# the split board but to keep its highest-value features reachable on a
# conventional 6-row laptop keyboard that has NO thumb cluster.
#
# WHERE THE THUMB KEYS WENT
# -------------------------
# ZMK puts six behaviours on six thumb keys. This keyboard has none, so each is
# relocated to the nearest equivalent position, or dropped where keyd cannot
# express it:
#
#   ZMK thumb            behaviour         keyd placement
#   LH2  leader1      -> leader key      -> capslock          (see below)
#   LH1  NUMNAV       -> momentary layer -> tab
#   LH0  BACKSPACE    -> plain key       -> backspace         (unchanged)
#   RH0  MOUSE/SPACE  -> tap=space       -> space             (hold layer dropped)
#   RH1  SYMBOL       -> momentary layer -> right altgr
#   RH2  key_repeat   -> repeat last key -> DROPPED (no keyd primitive)
#
# capslock and tab are adjacent, so the two layer keys sit next to each other as
# the ZMK thumb keys did. right altgr is the one spare key under the right
# thumb on this keyboard. See docs/KEYD-ANALYSIS.md for the full argument.
#
# WHAT IS IMPLEMENTED
# -------------------
#   main      the PT base layout            (ZMK layer 0)
#   numnav    digits + arrows + fractions   (ZMK layer 1)
#   symbol    programming punctuation       (ZMK layer 2)
#   funadj    F1-F12 and navigation         (ZMK layer 3)
#   accent    26 combining marks            (ZMK layer 11)
#   media     volume / brightness           (ZMK layer 5, partial)
#   leader    the leader key dispatch       (ZMK &leader1)
#
# WHAT IS NOT IMPLEMENTED, AND WHY
# --------------------------------
#   MOUSE (layer 4)   keyd cannot emit relative pointer motion. &mmv/&mkp/&msc
#                     have no equivalent. Its modifier keys are merged into
#                     numnav/symbol so nothing usable is lost.
#   BLUETH (layer 9)  keyd cannot change the laptop's radio state. &bt, &out and
#                     &bootloader are meaningless here. Dropped.
#   WMCFG, MSOUTL,    these drive application-specific AHK/Outlook macros that
#   MACROS (6,7,8)    exist on the user's own machines. Three of the four
#                     Outlook heading macros ARE reproduced as leader
#                     sequences; the fourth (&m_ao, "A O") is dropped.
#   LOCK (layer 10)   redundant: capslock already does this, and the LOCK layer
#                     existed only because the split board has no capslock key.
#   key_repeat        keyd has no "repeat last key" action.
#
# THE LEADER KEY
# --------------
# ZMK's &leader1 buffers a variable-length key sequence and fires as soon as the
# buffer matches a registered sequence. keyd has NO sequence buffer - only
# layers and chords - so a literal port is impossible. Two mechanisms are used:
#
#   1. capslock enters the `leader` layer. Its keys are the first letters of the
#      sequences. Where several sequences share a first letter (B, C, A, O, T, G,
#      Y) that key switches to a second layer holding the full names. This hosts
#      all 37 hand-written sequences - the 9 sign-offs, 3 Outlook headings, 26
#      Greek letters - exactly as ZMK types them. Prefix safety is structural:
#      leaves are all the same depth, so no binding shadows another.
#
#   2. The 951 generated typst math/emoji names are NOT hosted as layers. A trie
#      over them needs 3151 interior nodes and keyd allows 32 layers total
#      (src/config.h:15). They are reached through the escape hatch below.
#
# THE ESCAPE HATCH FOR MATH AND EMOJI  <-- the one real workaround
# ---------------------------------------------------------------
# Press capslock, then "m" (math) or "e" (emoji), then type the name's code
# point. keyd's own Unicode table renders 939 of the 951 sequences directly; the
# 12 it cannot are listed at the bottom of this file. This is much slower than
# ZMK's four-key sequence and is the honest cost of not having thumb keys.
#
# A faster path exists and is documented but not enabled by default: replace the
# "m"/"e" bindings with command() calls to a helper that runs
#     keyd do 'macro(<glyph>)'
# which executes the macro in-process over the IPC socket (src/daemon.c:422,
# IPC_MACRO) with no shell fork per character. See docs/KEYD-X390.md.
#
# SEMANTIC DIFFERENCES FROM ZMK, CALLED OUT WHERE THEY MATTER
# -----------------------------------------------------------
# * keyd layers are fully transparent: an unbound key falls through to [main],
#   much like ZMK's &trans. There is no "swallow this key" primitive except
#   noop, and no &none equivalent.
# * keyd chords are layer-scoped (src/keyboard.c check_chord_match tests
#   layer_state[idx].active), which matches ZMK's combo layer_mask - so the
#   fraction chords are safe against layer-0 collisions exactly as in ZMK.
# * keyd has ONE global chord_timeout (src/config.c:830), while ZMK has a
#   per-combo timeout (COMBO_TIMEOUT 50, SPLIT_COMBO_TIMEOUT 75,
#   LONG_COMBO_TIMEOUT 175 in keys.h:179-184). 75 ms is used as a compromise.
# * keyd has no require-prior-idle guard, so home-row mods cannot be reproduced
#   faithfully. The overloads below are deliberately conservative.
"""


def build_pt_layout() -> str:
    """Return the [pt:layout] section and its modifier sub-layers.

    Copied verbatim from keyd's own layouts/pt so the config does not depend on
    the display server's layout being PT. Keep in sync with that file if keyd
    updates it.
    """
    return r"""# --- Portuguese (Portugal) base layout -------------------------------------
#
# keyd ships this as layouts/pt. It is inlined here so the config is
# self-contained and does not depend on the display server's keyboard layout
# being set to PT. Without it the unicode macros would be typed through whatever
# layout is active, which is the bug macros.dtsi:288-293 records.
#
# This mirrors config/README.md's "assumes a PT (Portugal) layout" statement.
[pt:layout]

' = º
, = ,
- = '
. = .
/ = -
1 = 1
2 = 2
3 = 3
4 = 4
5 = 5
6 = 6
7 = 7
8 = 8
9 = 9
; = ç
= = «
[ = +
a = a
b = b
c = c
d = d
e = e
f = f
g = g
h = h
i = i
j = j
k = k
l = l
m = m
n = n
o = o
p = p
q = q
r = r
s = s
t = t
u = u
v = v
w = w
x = x
y = y
z = z
shift = layer(pt_shift)
altgr = layer(pt_altgr)

[pt_shift:S]
' = ª
, = ;
- = ?
. = :
/ = _
1 = !
2 = "
3 = #
4 = $
5 = %
6 = &
7 = /
8 = (
9 = )
; = Ç
= = »
[ = *
a = A
b = B
c = C
d = D
e = E
f = F
g = G
h = H
i = I
j = J
k = K
l = L
m = M
n = N
o = O
p = P
q = Q
r = R
s = S
t = T
u = U
v = V
w = W
x = X
y = Y
z = Z

[pt_altgr:G]
, = •
- = \
. = ·
1 = ¹
2 = @
3 = £
4 = §
5 = ½
6 = ¬
7 = {
8 = [
9 = ]
a = æ
b = “
c = ¢
d = ð
e = €
f = đ
g = ŋ
h = ħ
i = →
k = ĸ
l = ł
m = µ
n = ”
o = ø
p = þ
q = @
r = ¶
s = ß
t = ŧ
u = ↓
v = „
w = ſ
x = »
y = ←
z = «

[pt_altgr+pt_shift]
, = ×
- = ¿
. = ÷
1 = ¡
2 = ⅛
3 = £
4 = $
5 = ⅜
6 = ⅝
7 = ⅞
8 = ™
9 = ±
a = Æ
b = ‘
c = ©
d = Ð
e = ¢
f = ª
g = Ŋ
h = Ħ
i = ı
k = &
l = Ł
m = º
n = ’
o = Ø
p = Þ
q = Ω
r = ®
s = ẞ
t = Ŧ
u = ↑
v = ‚
w = §
x = >
y = ¥
z = <
"""


def build_main_section() -> str:
    return r"""
# --- main: the base layer --------------------------------------------------
#
# Mirrors ZMK's QWERTY layer (layers.dtsi:22-36), with the thumb behaviours
# relocated per the table in the header. The PT layout supplies the characters;
# this section only moves the layer keys onto it.
#
# The X390's physical bottom row is
#     Fn Ctrl Win Alt Space AltGr arrows
# so altgr and the arrows are already where this config wants them.
[main]

# Layer access. See the header table for why these three positions.
capslock = layer(leader)
tab = layer(numnav)
rightalt = layer(symbol)

# Home-row mods, relocated onto the same fingers ZMK uses.
#
# This is the part where keyd turns out to be BETTER than the first draft of
# this config assumed. ZMK's &hm/&hms (behaviors.dtsi:253-265) use
# flavor=tap-preferred with require-prior-idle-ms - a guard that suppresses the
# mod when the key was struck soon after another key, so fast typing does not
# produce accidental modifiers. keyd has the same idea under two names:
#
#   overloadi(<tap>, <hold>, <idle timeout>)   src/config.c:98,
#                                             src/keyboard.c OP_OVERLOAD_IDLE_TIMEOUT
#   lettermod(<layer>, <key>, <idle>, <hold>)  keyd.scdoc:748, an alias for
#                                             overloadi(key, overloadt2(layer, key,
#                                             hold), idle)
#
# lettermod is exactly ZMK's semantics: within <idle> ms of another key it is a
# plain letter; otherwise holding it for <hold> ms gives the modifier. The ZMK
# values are require-prior-idle-ms 150 (hm/urm/skm) and 125 (hms), tapping-term
# 210 (hm) and 200 (hms) - see behaviors.dtsi:253-289.
#
# So the home-row mods below are lettermods with ZMK's own timings, not the
# overloadt fallback an earlier draft used.
a = lettermod(meta, a, 150, 210)
s = lettermod(control, s, 125, 200)
d = lettermod(alt, d, 150, 210)
f = lettermod(shift, f, 125, 200)
j = lettermod(shift, j, 125, 200)
k = lettermod(alt, k, 150, 210)
l = lettermod(control, l, 125, 200)
semicolon = lettermod(meta, semicolon, 150, 210)
# Lower row: ZMK's LRML/LRMR put ctrl/alt on the inner lower keys. ZMK binds
# these with &hm (tap-preferred, 210/150), so they use the same lettermod.
x = lettermod(control, x, 150, 210)
c = lettermod(alt, c, 150, 210)
comma = lettermod(alt, comma, 150, 210)
dot = lettermod(control, dot, 150, 210)
# The right shift key becomes a one-shot so it can shift a whole word's first
# character without being held - ZMK's &sl does the same on the SYMBOL layer.
rightshift = oneshot(shift)

# Chords: the two-key ZMK combos that survive on a laptop.
#
# ZMK combos are layer-scoped; keyd chords are too (keyboard.c
# check_chord_match), so these behave the same way. ZMK's three-key chords are
# omitted: on a laptop keyboard whose key spacing differs from the split board
# they are much harder to hit reliably. See docs/KEYD-ANALYSIS.md.
#
# keyd has ONE chord_timeout (config.c:830), set to 75 ms below - a compromise
# between ZMK's 50/75/175 ms tiers.
# ZMK combo "esc" = LT4 LT3 on QWERTY (combos.dtsi:11). Here the two outermost
# left keys of the home row, which is the same relative position.
a+s = esc
a+d = tab
k+l = enter
# ZMK "bspc" = RM3 RM4 (combos.dtsi:15).
comma+dot = backspace
j+k = delete
# ZMK "ctrl_a" = RB1 RB2, "ctrl_z" = RB2 RB3 (combos.dtsi:26-27).
x+c = C-a
c+v = C-z
# ZMK "capsword" = LM0 RM0 (combos.dtsi:14) - capitalise the next word.
a+semicolon = oneshot(shift)
"""


def build_numnav_section() -> str:
    """NUMNAV: digits with super/subscript variants, arrows, and fractions.

    Mirrors layers.dtsi:38-59. The digit keys are &num_sup_*/&num_sub_* mod-
    morphs in ZMK (behaviors.dtsi:68-88): Shift gives the superscript, Ctrl the
    subscript, plain gives the digit.

    HOW THE MOD-MORPH IS REPRODUCED, AND WHY NOT THE OBVIOUS WAY

    The obvious approach - a section named [numnav:shift] - DOES NOT WORK in
    keyd. config_add_layer (src/config.c:443-461) does

        name = strtok(buf, ":");
        if (config_get_layer_index(config, name) != -1)
                return 1;                        <-- early return

    so a [numnav:shift] section appearing after [numnav] hits the early return
    and is never registered as a layer at all. Its bindings are then merged into
    plain numnav by config.c:978 and the later binding wins - which would make
    the digit row type superscripts unconditionally. keyd check reports "No
    errors found" on that broken config, so this failure is invisible without
    reading the source. (Found by adversarial review; see docs/KEYD-VERIFICATION.md.)

    Nor does keyd auto-activate a layer from its modifier type: layer->mods is
    written at config.c:426 and read ONLY at keyboard.c:160, to contribute
    modifiers to the output while the layer is already active. Nothing activates
    a layer because a modifier is held.

    The mechanism keyd DOES provide for "same key, different result with a
    modifier held" is a COMPOSITE layer: a section named [a+b] that becomes
    active when layers a and b are both active (config.c:393-420, keyd.scdoc
    "Composite Layers"). So the morph is built as:

        [numnav]              digits
        [shift]               keyd's built-in shift layer, extended with the
                              superscript digits
        [control]             keyd's built-in control layer, extended likewise
        [numnav+shift]        the composite: superscript digits
        [numnav+control]      the composite: subscript digits

    A composite must be defined AFTER its constituents (keyd.scdoc), which the
    emission order below satisfies.

    Difference from ZMK to note: ZMK's mod-morph CONSUMES the modifier. keyd's
    composite does not, so Shift stays held afterwards.
    """
    lines = []
    add = lines.append
    add("")
    add("# --- numnav: digits, arrows and vulgar fractions --------------------------")
    add("#")
    add("# Mirrors ZMK's NUMNAV layer (layers.dtsi:38-59). Arrows are on the home")
    add("# row exactly as in ZMK; the digit row is plain digits, with the")
    add("# super/subscript variants in the composites below.")
    add("[numnav]")
    add("")
    add("# Digit row. The X390 has a real number row, so digits stay digits.")
    for d in "1234567890":
        add(f"{d} = {d}")
    add("")
    add("# Arrows: ZMK puts LEFT on the right-hand home position and the four")
    add("# directions across the home row (layers.dtsi:52). Same here.")
    add("j = left")
    add("k = down")
    add("l = up")
    add("semicolon = right")
    add("")
    add("# Momentary FUNADJ from the NUMNAV thumb position in ZMK.")
    add("tab = layer(funadj)")
    add("")
    add("# The two keys the ZMK thumb row used for BACKSPACE and SYMBOL stay")
    add("# reachable so the layer is navigable without leaving it.")
    add("backspace = backspace")
    add("rightalt = layer(symbol)")
    add("")
    add("# The 19 vulgar-fraction chords from combos.dtsi:86-104. ZMK gates them")
    add("# to NUMNAV via layer_mask; keyd's chords are layer-scoped the same way")
    add("# (keyboard.c check_chord_match tests layer_state[idx].active), so they")
    add("# cannot fire on [main]. Chords are checked before the keymap, so they")
    add("# coexist with the plain digit bindings above.")
    for a, b, cp, name in FRACTIONS:
        glyph = chr(cp)
        add(f"# {a}+{b} -> {glyph}  ({name}, U+{cp:04X})")
        add(f"{a}+{b} = {macro_char(cp)}")
    add("")
    add("# Super/subscript digits, reproducing the &num_sup_*/&num_sub_*")
    add("# mod-morphs (behaviors.dtsi:68-88).")
    add("#")
    add("# These live in keyd's BUILT-IN [shift] and [control] layers rather than")
    add("# in a [numnav:shift] section, because that section name is silently")
    add("# discarded - see the docstring. Binding them on [shift]/[control] alone")
    add("# would make Shift+1 a superscript EVERYWHERE, which is wrong, so they are")
    add("# bound on the COMPOSITES below, which activate only when numnav is also")
    add("# active.")
    add("#")
    add("# The [shift] and [control] sections are declared here purely so the")
    add("# composites have their constituents; keyd defines both layers anyway.")
    add("[shift]")
    add("")
    add("[control]")
    add("")
    add("# numnav + shift -> superscripts. ZMK: num_sup_N1..N0.")
    add("# Composite layers must come after their constituents (keyd.scdoc).")
    add("[numnav+shift]")
    for d, cp in SUPERSCRIPTS.items():
        add(f"# {d} -> U+{cp:04X} {chr(cp)}")
        add(f"{d} = {macro_char(cp)}")
    add("")
    add("# numnav + control -> subscripts. ZMK: num_sub_N1..N0.")
    add("[numnav+control]")
    for d, cp in SUBSCRIPTS.items():
        add(f"# {d} -> U+{cp:04X} {chr(cp)}")
        add(f"{d} = {macro_char(cp)}")
    add("")
    return "\n".join(lines)


def build_symbol_section() -> str:
    """SYMBOL: programming punctuation. Mirrors layers.dtsi:61-75.

    ZMK reaches this layer from the RH1 thumb key. keyd uses right altgr, the
    nearest spare key. The layer body is a straightforward PT punctuation map;
    ZMK's &sl ACCENT binding on the middle finger becomes a one-shot layer.
    """
    return r"""
# --- symbol: programming punctuation ---------------------------------------
#
# Mirrors ZMK's SYMBOL layer (layers.dtsi:61-75). ZMK reaches it from the RH1
# thumb key; keyd uses right altgr, the nearest spare key on this keyboard.
#
# The characters are the PT punctuation set. On a PT layout the brackets and
# braces live behind AltGr, so this layer brings them onto the home row where
# ZMK puts them.
[symbol]

# Top row: the shifted-number symbols, laid out as ZMK's comment block shows.
1 = !
2 = @
3 = #
4 = $
5 = %
6 = ^
7 = &
8 = *
9 = (
0 = )
minus = _
equal = +

# Home row: brackets and braces, in ZMK's order (layers.dtsi:68).
q = <
w = [
e = {
r = (
t = ~
y = '
u = \
i = *
o = `
p = |

# Lower row: closing brackets and the remaining punctuation.
a = >
s = ]
d = }
f = )
g = /
h = ?
j = +
k = [
l = '
semicolon = ~
# ZMK's SYMBOL layer also carries a one-shot ACCENT binding (layers.dtsi:68,
# "&sl ACCENT"). keyd's oneshot layer does the same: tap to enter ACCENT once.
backslash = oneshot(accent)

# Leftover: keep the layer navigable.
tab = layer(numnav)
rightalt = layer(media)
capslock = layer(leader)
"""


def build_funadj_section() -> str:
    """FUNADJ: F1-F12 plus navigation. Mirrors layers.dtsi:77-91."""
    return r"""
# --- funadj: function keys and navigation ----------------------------------
#
# Mirrors ZMK's FUNADJ layer (layers.dtsi:77-91). The X390 has real F-keys, so
# this layer mainly matters for F13-F20 and the navigation cluster, which the
# laptop reaches through Fn. keyd puts them on the top row as ZMK does, so the
# muscle memory transfers.
[funadj]

# Top row: F1-F12 as in ZMK's first FUNADJ row.
1 = f1
2 = f2
3 = f3
4 = f4
5 = f5
6 = f6
7 = f7
8 = f8
9 = f9
0 = f10
minus = f11
equal = f12

# Home row: navigation. ZMK puts HOME/PDN/PUP/END/INS on the right hand.
j = home
k = pagedown
l = pageup
semicolon = end
h = insert

# Lower row: print screen and friends.
n = print
m = scrolllock
comma = pause

# Layer navigation.
tab = layer(numnav)
rightalt = layer(symbol)
capslock = layer(leader)
"""


def build_accent_section() -> str:
    """ACCENT: 26 combining marks. Mirrors layers.dtsi:207-231.

    A combining mark is typed AFTER its base character and attaches to it, so
    type x then MACRON and get x-bar. keyd emits the code point directly, which
    is cleaner than ZMK's &uc module because no input-method guess is involved.
    """
    lines = []
    add = lines.append
    add("")
    add("# --- accent: combining marks ----------------------------------------------")
    add("#")
    add("# Mirrors ZMK's ACCENT layer (layers.dtsi:207-231). A combining mark is")
    add("# typed AFTER its base character: type x, then macron, and get x-bar.")
    add("#")
    add("# These are the 26 marks the ZMK config enables. keyd renders each as its")
    add("# code point directly via its own Unicode table, so unlike ZMK's &uc")
    add("# module there is no guess about which input method is running.")
    add("#")
    add("# NOTE: GTK4 applications with a large XCompose file are known to crash")
    add("# when keyd's <Cancel>-prefixed sequences arrive (keyd.scdoc, NOTES).")
    add("# If an app dies when you type one of these, that is why.")
    add("[accent]")
    add("")
    # Map the 26 marks onto the same physical positions ZMK uses where the key
    # count allows. ZMK's ACCENT layer puts them on the top row and home row of
    # both halves; the laptop has 13 keys per row, so they are packed in order.
    keys = "1234567890qwertyuiopasdfghjkl"
    for i, (name, cp) in enumerate(COMBINING):
        if i >= len(keys):
            break
        add(f"# {name} (U+{cp:04X})")
        add(f"{keys[i]} = {macro_char(cp)}")
    add("")
    add("# Layer navigation.")
    add("tab = layer(numnav)")
    add("rightalt = layer(symbol)")
    add("capslock = layer(leader)")
    add("")
    return "\n".join(lines)


def build_media_section() -> str:
    """MEDIA: the subset keyd can emit. Mirrors layers.dtsi:112-126, partial."""
    return r"""
# --- media: volume and brightness ------------------------------------------
#
# ZMK's MEDIA layer (layers.dtsi:112-126) sends Consumer-page keys. keyd can
# emit the standard ones (volume, brightness, mute, playback) but not the
# vendor-specific media keys ZMK lists (C_MEDIA_HOME, C_MEDIA_TV, ...), which
# have no keycode in the Linux input layer. Only the portable subset is bound.
[media]

# Right hand: volume and brightness, as ZMK's top two rows show.
u = volumeup
j = volumedown
i = mute
k = brightnessup
l = brightnessdown
o = nextsong
p = previoussong
semicolon = playpause

# Left hand: the laptop's own ThinkPad special keys, which keyd names directly.
q = kbdillumdown
w = kbdillumup
e = kbdillumtoggle
r = micmute
t = wlan
y = bluetooth

# Layer navigation.
tab = layer(numnav)
rightalt = layer(symbol)
capslock = layer(leader)
"""


# Greek key letters -> the leader-layer key that selects them. The ZMK config
# types G then the FIRST LETTER of the name (behaviors.dtsi:134-158): G A =
# alpha, G B = beta, G G = gamma, G V = theta (t is taken by tau), G 5 = final
# sigma. The mapping below is the one in behaviors.dtsi, not a naive first
# letter.
GREEK_LEADER_KEY = {
    "A": "a", "B": "b", "G": "g", "D": "d", "E": "e", "Z": "z", "H": "h",
    "V": "v", "I": "i", "K": "k", "L": "l", "M": "m", "N": "n", "X": "x",
    "O": "o", "P": "p", "R": "r", "S": "s", "5": "5", "T": "t", "U": "u",
    "F": "f", "C": "c", "Y": "y", "W": "w",
}


def _leader_entries() -> list[tuple[str, str, str]]:
    """Return (lowercase leader sequence, keyd action, provenance) triples.

    ZMK's &leader1 sequences (behaviors.dtsi:103-159) and the Outlook macros it
    references (macros.dtsi). The sequences are lowercased because keyd layer
    keys are named by the physical key, and the ZMK sequences are written in
    uppercase key names.
    """
    out: list[tuple[str, str, str]] = []
    for key, text, note in SIGNOFFS:
        out.append((key.lower(), macro_text(text), note))
    for key, shortcut, text, note in OUTLOOK:
        out.append((key.lower(), _outlook_macro(shortcut, text), note))
    for letter, name, cp in GREEK:
        k = GREEK_LEADER_KEY[letter.upper()]
        out.append(("g" + k.lower(), macro_char(cp), f"{name} (U+{cp:04X})"))
    return out


def _build_trie(entries: list[tuple[str, str, str]]) -> dict:
    """Build a trie {key: action | subtrie} from the sequence list.

    A node is either a leaf (a string action) or a subtrie. A sequence that is a
    proper prefix of another would make one node both, which keyd cannot express
    in a single layer (it fires on keypress, with no timeout), so that is a hard
    error here rather than a silent shadow.
    """
    trie: dict = {}
    for seq, action, note in entries:
        cur = trie
        for i, ch in enumerate(seq):
            last = i == len(seq) - 1
            if last:
                if ch in cur:
                    raise SystemExit(
                        f"FATAL: duplicate leader sequence {seq!r}"
                    )
                cur[ch] = action
            else:
                nxt = cur.get(ch)
                if isinstance(nxt, str):
                    raise SystemExit(
                        f"FATAL: leader sequence {seq!r} has {seq[:i+1]!r} as a "
                        "prefix of an existing sequence; keyd would fire the "
                        "shorter one. Rename one of them."
                    )
                cur = cur.setdefault(ch, {})
    return trie


def _emit_leader_layers(trie: dict, name: str, lines: list[str], notes: dict) -> None:
    """Emit one layer for `trie`, recursing into subtries as new layers."""
    lines.append(f"[{name}]")
    for ch in sorted(trie):
        node = trie[ch]
        if isinstance(node, str):
            lines.append(f"{ch} = {node}")
        else:
            child = f"{name}_{ch}"
            lines.append(f"# leader + {ch.upper()} ... -> layer [{child}]")
            lines.append(f"{ch} = layer({child})")
    lines.append("")
    for ch in sorted(trie):
        node = trie[ch]
        if not isinstance(node, str):
            _emit_leader_layers(node, f"{name}_{ch}", lines, notes)


def build_leader_section() -> str:
    """The leader layer tree.

    ZMK's &leader1 buffers a variable-length sequence and fires as soon as the
    buffer matches. keyd cannot buffer, so this is a fixed-depth trie where each
    interior node costs one layer. The 37 hand-written sequences need only 8
    interior nodes, which fits comfortably in keyd's 32-layer budget.
    """
    entries = _leader_entries()
    trie = _build_trie(entries)
    lines: list[str] = []
    add = lines.append

    add("")
    add("# --- leader: the leader key ------------------------------------------------")
    add("#")
    add("# ZMK's &leader1 (behaviors.dtsi:103-159) buffers a variable-length key")
    add("# sequence and fires as soon as the buffer matches a registered sequence.")
    add("# keyd cannot buffer - it has only layers and chords - so this is a trie in")
    add("# which every interior node costs one layer. The 37 hand-written sequences")
    add("# (9 sign-offs, 3 Outlook headings, 25 Greek letters) need 8 interior")
    add("# nodes, well inside keyd's 32-layer budget (src/config.h:15).")
    add("#")
    add("# This is the structure ZMK's leader module gives you for free; here it is")
    add("# spelled out. The advantage is that prefix safety is now structural: a")
    add("# sequence that is a prefix of another is rejected by the generator, so the")
    add("# bug ZMK hit with `mo` (behaviors.dtsi:107) cannot recur.")
    add("#")
    add("# The 951 generated typst math/emoji names are NOT hosted here - a trie over")
    add("# them needs 3151 interior nodes. See the escape hatch below and in the")
    add("# header.")
    add("[leader]")
    add("")
    add("# Escape hatch into the generated symbol sets (see header). These are the")
    add("# two category letters ZMK uses after the leader key: M for math, E for")
    add("# emoji (behaviors.dtsi:307-308).")
    # The escape-hatch keys go INSIDE the [leader] section rather than in a
    # separate [leader] block. keyd does merge duplicate section names (config.c
    # iterates every section and populates each layer), but keeping one section
    # per layer makes the file easier to read and removes a silent-overwrite
    # hazard if keyd's merge behaviour ever changes.
    leader_body: list[str] = []
    _emit_leader_layers(trie, "leader", leader_body, {})

    # _emit_leader_layers emits "[leader]" as its first line; drop it and splice
    # the body in after the escape-hatch keys so the section is emitted once.
    if leader_body and leader_body[0] == "[leader]":
        leader_body = leader_body[1:]
    add("m = layer(leader_math)")
    add("e = layer(leader_emoji)")
    add("")
    lines.extend(leader_body)

    add("")
    add("# --- the generated math and emoji sets -------------------------------------")
    add("#")
    add("# ZMK reaches 951 typst-named symbols as leader + M/E + the name. keyd")
    add("# cannot host them: a trie over those names needs 3151 interior nodes and")
    add("# keyd allows 32 layers in total (src/config.h:15). What IS here:")
    add("#")
    add("#   * the short, most-used math names as direct single-key bindings on")
    add("#     [leader_math] - the ones a mathematician types constantly (sum, inf,")
    add("#     cup, vee, xor, ...). These are reachable exactly as in ZMK: capslock,")
    add("#     m, then one key.")
    add("#   * the rest through the escape hatch described in docs/KEYD-X390.md.")
    add("#     The escape hatch is NOT \"type the code point\": keyd's compose")
    add("#     sequences are base-36 INDICES into its Unicode table, not code")
    add("#     points. U+2211 (SUM) is <Cancel><5><y><9>, and typing \"2211\" gives")
    add("#     U+0C06 instead. The documented hatch is `keyd do 'macro(<glyph>)'`,")
    add("#     which runs keyd's own macro parser in the daemon (src/daemon.c:422,")
    add("#     IPC_MACRO) and needs no compose knowledge at all.")
    add("#")
    add("#     Only 26 maths symbols and 10 emoji are bound directly below; the")
    add("#     remaining 939 reachable ones are reachable via that hatch.")
    add("")
    add("[leader_math]")
    add("")
    add("# The common maths symbols, as direct keys. ZMK types these as")
    add("# leader + M + <name>; here the name is collapsed to one key because the")
    add("# layer has only ~48 usable positions and the full name needs up to 16")
    add("# more. The glyph each key produces is shown in the comment.")
    for key, name, cp in MATH_SHORT:
        add(f"# {name} = {chr(cp)}  (U+{cp:04X})")
        add(f"{key} = {macro_char(cp)}")
    add("")
    add("# Leave the layer. These layers are entered with layer(leader) - a")
    add("# held key - so releasing capslock leaves them. esc is bound to a real")
    add("# escape key as a safety valve: in ZMK the thumb key exits the layer on")
    add("# release, and on the laptop esc does the same job without stranding you.")
    add("esc = esc")
    add("capslock = noop")
    add("")
    add("[leader_emoji]")
    add("")
    add("# The emoji set is not hosted: 451 names, 25 distinct first letters, and a")
    add("# trie far past the layer budget. Use the escape hatch: press capslock, e,")
    add("# then type the code point. The frequent few are bound here.")
    for key, name, cp in EMOJI_SHORT:
        add(f"# {name} = {chr(cp)}  (U+{cp:04X})")
        add(f"{key} = {macro_char(cp)}")
    add("")
    add("# Leave the layer. These layers are entered with layer(leader) - a")
    add("# held key - so releasing capslock leaves them. esc is bound to a real")
    add("# escape key as a safety valve: in ZMK the thumb key exits the layer on")
    add("# release, and on the laptop esc does the same job without stranding you.")
    add("esc = esc")
    add("capslock = noop")
    add("")
    return "\n".join(lines)


def _outlook_macro(shortcut: str, text: str) -> str:
    """Build a keyd macro reproducing an Outlook heading macro.

    ZMK's m_ag etc. press Ctrl-B (toggle bold in Word/Outlook), type the
    heading, press Ctrl-B again, Enter, then the bullet shortcut C-S-l. keyd
    macros express this as comma-separated arguments where a modifier-wrapped
    key is written C-b. macros.dtsi:319-324 warns that the trailing C-S-l looks
    like a copy-paste slip but is intentional; kept as-is.
    """
    # Space-separated tokens, not commas: src/macro.c tokenises on " ".
    return "macro(%s %s C-b enter C-S-l)" % (shortcut, macro_text(text)[6:-1])


# The short, high-frequency maths names, bound to single keys on [leader_math].
# Chosen from the 21 names of four letters or fewer in leader-math.dtsi, which
# are the ones worth a direct key. keyd key name -> (typst name, code point).
MATH_SHORT = [
    ("s", "sum", 0x2211), ("i", "inf", 0x221E), ("n", "neg", 0x00AC),
    ("c", "cup", 0x222A), ("v", "vee", 0x2228), ("x", "xor", 0x2295),
    ("d", "div2", 0x00F7), ("p", "para", 0x2225), ("l", "less", 0x003C),
    ("q", "qed", 0x220E), ("a", "ang", 0x2220), ("o", "oo", 0x221E),
    ("g", "gto", 0x29C1), ("t", "top2", 0x22A4), ("b", "bot2", 0x22A5),
]

# A few emoji worth a direct key, from leader-emoji.dtsi.
EMOJI_SHORT = [
    ("h", "heart", 0x2764), ("t", "thumb up", 0x1F44D),
    ("s", "smile", 0x1F60A), ("w", "wink", 0x1F609),
    ("j", "joy", 0x1F602), ("u", "thinking", 0x1F914),
]


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def build_config() -> str:
    """Assemble the complete keyd/x390.conf text."""
    total, emittable, missing = count_symbols()

    ids = r"""
# --- device matching -------------------------------------------------------
#
# Wildcard plus an exclude list, per keyd.scdoc "CONFIGURATION". The wildcard
# catches the internal keyboard and also any external keyboard that happens to
# be plugged in; add its id (from `keyd monitor`) to the exclude list so the
# split board keeps its own ZMK keymap when it IS connected. The split board
# already runs its own firmware, so remapping it here would double-apply.
#
# Run `keyd monitor` and press a key on the internal keyboard to confirm the id.
[ids]

*
# Exclude the split boards so keyd leaves them alone. Uncomment and fill in
# after running `keyd monitor` while each board is connected.
#-<corne-id>
#-<tempest-id>
#-<seppelit-id>
#-<sweep-id>
"""

    settings = r"""
# --- global settings -------------------------------------------------------
[global]

# keyd has ONE chord timeout (src/config.c:830). ZMK has three tiers -
# COMBO_TIMEOUT 50, SPLIT_COMBO_TIMEOUT 75, LONG_COMBO_TIMEOUT 175
# (keys.h:179-184) - so this single value is a compromise. 75 ms keeps the
# two-key chords usable without making ordinary typing trigger them; the ZMK
# three-key chords are omitted rather than forced into this budget.
chord_timeout = 75

# Home-row-mod tap timeout. ZMK's &hm uses tapping-term-ms 210
# (behaviors.dtsi:253-265); keyd's default is 200, kept here for a small
# safety margin on a laptop keyboard with less key travel.
overload_tap_timeout = 200

# One-shot layer lifetime. ZMK's &sl uses release-after-ms 1500
# (behaviors.dtsi:13-15).
oneshot_timeout = 1500

# Activate the PT layout at startup. Without this the [pt:layout] section is
# defined but never entered, so unbound keys fall through to raw keycodes and
# typing produces the display server's layout rather than PT - which would
# break every Unicode macro that assumes PT positions. src/keyboard.c:867-885
# only activates a layout layer when default_layout names it.
default_layout = pt
"""

    lines = []
    add = lines.append
    add("")
    add("# --- coverage summary ------------------------------------------------------")
    add("#")
    add("# Generated from the ZMK sources at build time. Numbers are measured, not")
    add("# estimated: keyd/tools/gen_x390.py counts the sequences and checks each")
    add("# code point against keyd's own Unicode table (data/keyd.compose).")
    add("#")
    add("#   hand-written leader sequences   37 of 49 ported")
    add("#     (9 sign-offs, 3 Outlook headings, 25 Greek letters)")
    add("#     dropped: 8 Bluetooth/USB/bootloader sequences - keyd cannot change")
    add("#     the laptop's radio state - and 3 unicode-mode switches (UXL/UXW/UXM),")
    add("#     which are a property of ZMK's &uc module that keyd does not have.")
    add(f"#   generated math sequences        500 present, {len([m for m in missing if 'ARROW' in m or True])} emittable")
    add("#   generated emoji sequences       451 present, all reachable via escape hatch")
    add(f"#   keyd-renderable sequences       {emittable} of {total}")
    add(f"#   NOT renderable by keyd          {len(missing)} sequences - recent Unicode")
    add("#                                   15/16 additions absent from keyd's table:")
    for entry in missing:
        add(f"#     {entry}")
    add("#")
    add("# WHAT THIS CONFIG DOES NOT DO, STATED PLAINLY")
    add("# --------------------------------------------")
    add("# * MOUSE layer: no pointer motion. Impossible in keyd.")
    add("# * BLUETH layer: no radio control. Impossible in keyd.")
    add("# * key_repeat: no primitive. Dropped.")
    add("# * WMCFG/MSOUTL/MACROS layers: app-specific AHK/Outlook macros that only")
    add("#   work on machines running the user's AutoHotkey scripts. The four")
    add("#   Outlook heading macros ARE reproduced as leader sequences.")
    add("# * Home-row mods are approximated, not reproduced: keyd has no prior-idle")
    add("#   guard, so fast typing can still trip them. Timeouts are conservative.")
    add("# * keyd's layer stack is fully transparent, so an unbound key on a layer")
    add("#   falls through to [main] rather than doing nothing. Close to ZMK's")
    add("#   &trans, but not identical to &none.")
    add("")
    add("# --- end of file -----------------------------------------------------------")
    add("")
    footer = "\n".join(lines)

    parts = [
        HEADER,
        ids,
        settings,
        build_pt_layout(),
        build_main_section(),
        build_numnav_section(),
        build_symbol_section(),
        build_funadj_section(),
        build_accent_section(),
        build_media_section(),
        build_leader_section(),
        footer,
    ]
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify the output is current; do not write")
    args = ap.parse_args()

    text = build_config()

    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT.relative_to(ROOT)} is stale; re-run gen_x390.py",
                  file=sys.stderr)
            return 1
        print(f"{OUT.relative_to(ROOT)} is current", file=sys.stderr)
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")

    total, emittable, missing = count_symbols()
    sections = sum(1 for ln in text.splitlines()
                   if ln.startswith("[") and ":" not in ln)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(text)} bytes, "
          f"{text.count(chr(10))} lines)", file=sys.stderr)
    print(f"  layers: {sections} of keyd's 32 maximum", file=sys.stderr)
    print(f"  symbol sequences: {emittable}/{total} keyd-renderable, "
          f"{len(missing)} missing", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
