# keyd on a conventional pt_PT keyboard

This is the practical guide to `keyd/pt_pt.conf`: how to install it, how to reach
the features that ZMK puts on thumb keys, and an honest account of what is not
possible. The design reasoning is in [KEYD-ANALYSIS.md](KEYD-ANALYSIS.md); the
generated config is `keyd/pt_pt.conf`, produced by `keyd/tools/gen_pt_pt.py`.

---

## The short answer

**Your thumb keys did not vanish — they moved to the two keys either side of
where your thumbs rest.**

| ZMK thumb | what it does | new home |
|---|---|---|
| `LH2` leader | press, then a short sequence | **CapsLock** |
| `LH1` NUMNAV | digits and arrows | **Tab** |
| `LH0` backspace | backspace | **Backspace** (unchanged) |
| `RH0` space/MOUSE | tap = space | **Space** (hold-for-mouse dropped) |
| `RH1` SYMBOL | programming punctuation | **right AltGr** |
| `RH2` key_repeat | repeat last key | **dropped** |

CapsLock and Tab are adjacent on a conventional keyboard's bottom-left, so the
two layer keys sit together exactly as the ZMK thumb cluster did. Right AltGr is
the spare key under your right thumb. That is the closest a 6-row keyboard gets
to a thumb cluster.

---

## Install

```sh
# Arch
sudo pacman -S keyd

# copy the config into place
sudo mkdir -p /etc/keyd
sudo cp keyd/pt_pt.conf /etc/keyd/

# validate BEFORE enabling the daemon
sudo keyd check /etc/keyd/pt_pt.conf

sudo systemctl enable --now keyd
```

Then find the keyboard's id and exclude your split boards so keyd leaves them
alone:

```sh
sudo keyd monitor        # press a key on each device, note the id
```

Put each split-board id in the `[ids]` exclude list at the top of the config
(`-0123:4567`), so keyd never touches a board that already runs ZMK.

### Checking your work

Two scripts in `keyd/tools/` are part of the deliverable:

```sh
python3 keyd/tools/gen_pt_pt.py --check   # config matches its generator
python3 keyd/tools/audit.py              # structural checks keyd check misses
python3 keyd/tools/coverage.py           # unicode coverage of the symbol sets
```

`keyd check` only validates syntax. It happily accepts a layer that binds the
same key twice (silently keeping one), a layer nothing reaches, or a key name
that resolves to nothing. `audit.py` checks those.

---

## How to trigger the thumb-key features

### Leader (was `LH2`)

Press **CapsLock**, then the sequence. This reproduces ZMK's `&leader1`:

| sequence | result |
|---|---|
| CapsLock `o` `b` `r` | "Obrigado,\nHeiko" |
| CapsLock `c` `u` | "Cumps,\nHeiko" |
| CapsLock `b` `r` | "Best regards,\nHeiko" |
| CapsLock `t` `y` | "Thank you,\nHeiko" |
| CapsLock `y` `w` | "You're Welcome" |
| CapsLock `a` `g` | Outlook "Agenda:" block |
| CapsLock `o` `b` `j` | Outlook "Objective:" block |
| CapsLock `g` `g` | γ |
| CapsLock `g` `v` | θ |
| CapsLock `g` `5` | ς |

All 25 Greek letters and all 9 sign-offs work this way — same mnemonics as ZMK.
The full list is in the generated config's `[leader]` tree.

### NUMNAV (was `LH1`) — Tab

Hold **Tab**. Digits stay digits; arrows are on `j k l ;`. The 19 vulgar
fractions are chords on the digit keys, exactly as in ZMK: `1+2` → ½, `3+4` → ¾,
`1+4` → ¼. Hold Shift for superscripts (2 → ²), Ctrl for subscripts (2 → ₂).

### SYMBOL (was `RH1`) — right AltGr

Hold **right AltGr**. Programming punctuation on the home row as in ZMK's layer
map. Backslash is a one-shot ACCENT: tap it to type one combining mark.

### ACCENT — reached from SYMBOL

Hold right AltGr, tap `\`, then type your base character and the mark attaches:
`x` then macron gives x̄. The 26 marks are on the top two rows.

### FUNADJ — from NUMNAV or SYMBOL

Hold Tab, then **Tab** again to reach FUNADJ: F1–F12 on the number row,
Home/End/PgUp/PgDn/Insert on the home row.

### MEDIA — from SYMBOL

Hold right AltGr, then `right AltGr` again for MEDIA: volume on `u`/`j`,
brightness on `k`/`l`, and the vendor media/special keys if your keyboard has
them (mic mute, wifi, bluetooth, keyboard backlight) on the left hand.

### Chords (replacing ZMK combos)

Two-key chords on the base layer, matching ZMK's positions:

| chord | result |
|---|---|
| `a` + `s` | Esc |
| `a` + `d` | Tab |
| `k` + `l` | Enter |
| `,` + `.` | Backspace |
| `j` + `k` | Delete |
| `x` + `c` | Ctrl-A |
| `c` + `v` | Ctrl-Z |

The chord set matches ZMK's, with one deliberate divergence in mechanism. ZMK's
`C`+`V` chord now sends the code point U+00DF through the `&uc` unicode
behaviour, so the host helper types ß; keyd instead maps `s` on `[pt_altgr]`
straight to the character (`s = ß`, with `s = ẞ` on `[pt_altgr+pt_shift]`),
which the host layout resolves natively. Same output, different mechanism —
keyd remaps the host layout, the ZMK board cannot.

---

## Math and emoji: the honest limitation

ZMK reaches **500 math symbols and 451 emoji** with leader + `M`/`E` + the
typst name. keyd **cannot do this**, and it is worth being precise about why:

ZMK's leader buffers a variable-length key sequence and fires when the buffer
matches. keyd has no sequence buffer — only *layers* (a key → an action) and
*chords* (keys pressed together → an action). Reaching 951 multi-letter names
that way needs a trie whose interior nodes are layers: **3167 of them**. keyd
allows **32 layers in total**. So a literal port is not a matter of effort; the
arithmetic rules it out.

What the config does instead, in order of usefulness:

1. **The ~15 most-used math symbols get a direct key.** CapsLock `m` `s` → ∑,
   `m` `i` → ∞, `m` `c` → ∪, `m` `x` → ⊕, and so on. These are the ones you
   actually type while writing maths.
2. **Everything else via the escape hatch.** Every one of the 951 sequences has
   a Unicode code point that keyd can render — except 12 (listed at the end of
   the config; all Unicode 15/16 additions missing from keyd's table). So type
   the code point. Slower, but nothing is unreachable.
3. **The faithful path, documented but not enabled.** keyd has an IPC socket and
   a `command()` action, so a small helper could resolve a typed name and hand
   the glyph back with `keyd do 'macro(<glyph>)'`. That executes in-process
   (no shell fork per keypress) and would behave almost like ZMK. It is not
   enabled because it needs a helper process, and a config that shells out on
   every keypress is not something to ship as the default. See "Going further".

---

## What is not possible at all

These are limits of what keyd *is*, not of this config:

| ZMK feature | why keyd cannot do it |
|---|---|
| **MOUSE layer** | keyd remaps keys; it cannot emit relative pointer motion. `&mmv`, `&mkp`, `&msc` have no equivalent. |
| **BLUETH layer** | keyd cannot change the keyboard's radio state. `&bt`, `&out`, `&bootloader` are meaningless. |
| **key_repeat** | keyd has no "repeat last key" action. |
| **Home-row mods** | *Not* a limitation after all — keyd has `lettermod`, which is ZMK's prior-idle guard under another name. See below. |
| **WMCFG / MSOUTL / MACROS layers** | These drive AHK/Outlook macros that only work on machines running the user's AutoHotkey scripts. The four Outlook *heading* macros are reproduced as leader sequences. |

### Home-row mods: better than expected

An earlier draft of this config assumed keyd could not reproduce ZMK's
`require-prior-idle-ms` guard. That was wrong. keyd has **`lettermod`**, which is
the same idea with a different name:

```conf
a = lettermod(meta, a, 150, 210)
```

Reads as: within 150 ms of another key, `a` is just a letter (no delay, no
modifier); otherwise, holding it 210 ms gives the modifier. Those are exactly
ZMK's `&hm` values (`tapping-term-ms 210`, `require-prior-idle-ms 150`,
`behaviors.dtsi:253-257`), and the config uses ZMK's own numbers throughout.

### The math/emoji escape hatch — read this before using it

The instruction "type the code point" is **wrong**, and getting it wrong is
easy. keyd's compose sequences are base-36 *indices* into its Unicode table, not
code points: `∑` (U+2211) is `<Cancel> <5> <y> <9>`, and typing `2211` produces
`ఆ` (U+0C06), not `∑`.

The correct hatch is keyd's own macro evaluator:

```sh
keyd do 'macro(∑)'
```

That runs keyd's real `macro_parse` in the daemon and emits the glyph. Bind it to
a key with `command(...)` and you have a working escape hatch that needs no
compose knowledge:

```conf
[leader_math]
# ... after a prefix layer resolves a name, hand the glyph back:
s = command(keyd do 'macro(∑)')
```

26 maths symbols and 10 emoji are already bound directly on `[leader_math]` and
`[leader_emoji]`; the rest need this hatch.

---

## Going further: a faithful leader

If the escape hatch is too slow for daily maths, this is the upgrade path. keyd
can execute an arbitrary macro in-process over its IPC socket
(`src/daemon.c`, `IPC_MACRO`), so a helper daemon can own the leader state:

1. The helper reads key events (`keyd listen`, or its own evdev reader).
2. On the leader key it starts buffering key names.
3. When the buffer matches a name from `leader-math.dtsi`/`leader-emoji.dtsi`, it
   calls `keyd do "macro(<glyph>)"` — the glyph appears as if typed.
4. On timeout or a non-matching key, it drops the buffer.

That reproduces ZMK's model exactly, including prefix resolution. The catch is
that it is a separate process to keep running and to keep in sync with the ZMK
sources — which is why it is documented here rather than implemented in the
shipped config. The generated symbol tables would be reused as-is, so there is
no second source of truth.

---

## Differences from ZMK you will notice

* **Layer transparency.** keyd layers fall through to `[main]` for unbound keys.
  This is close to ZMK's `&trans`, but there is no exact `&none` — a key on a
  layer that you did not bind does its base-layer action, it does not do nothing.
* **One chord timeout.** ZMK has three tiers (50/75/175 ms); keyd has one global
  value. It is set to 75 ms. The three-finger ZMK chords are therefore omitted —
  on a conventional keyboard's key spacing they are hard to hit reliably anyway.
* **Modifiers are not consumed.** ZMK's mod-morphs swallow the modifier that
  triggered them; keyd's modifier layers leave it held. This only matters when
  chaining shortcuts.
* **GTK4 and XCompose.** keyd emits non-ASCII characters as a `<Cancel>` plus
  three base-36 digits, resolved through an XCompose file. GTK4 applications
  with a very large XCompose file are known to crash on those sequences. If an
  application dies when you type a combining mark or a symbol, this is why.
