# Heiko's zmk-config for corne / tempest / seppelit / sweep

<!--toc:start-->
- [Heiko's zmk-config for corne / tempest / seppelit / sweep](#heikos-zmk-config-for-corne--tempest--seppelit--sweep)
  - [Overview](#overview)
  - [One layout, four keyboards](#one-layout-four-keyboards)
  - [Leader key: symbols, emoji and text snippets](#leader-key-symbols-emoji-and-text-snippets)
  - [Repository layout](#repository-layout)
  - [Editing the keymap](#editing-the-keymap)
  - [Building and flashing](#building-and-flashing)
  - [Keymaps](#keymaps)
<!--toc:end-->

## Overview

The repo contains my personal ZMK keyboard layout.

I am programming in Python, Rust, Bash/POSIX, and a bit of Java.
At the same time I am writing to almost equal degree in Portuguese, English
and German.

Due to that usage pattern I require quick and easy access to all special characters
and numbers used for programming while also allowing the access quickly the Portuguese
accents and German umlauts.
The Portuguese keyboard layout is the most appropriate to cover all necessary symbols.
While the US or even UK English layout is superior for programming, it does not cover
some Portuguese letters like "ç" (C-Cedilha) nor German Umlauts.

For this reason this ZMK keymap assumes the configuration of a PT (Portugal) keyboard
layout (macOS/Linux/Android).

Both German and Portuguese keyboard layouts are terrible for programming,
but this is taken care of by the layers. There are some layers for specific
applications with bad default support for keyboard centric workflows
(e.g. MS Outlook).

## One layout, four keyboards

All four keyboards share a **single** keymap definition. Each keyboard has a
small adapter file that selects its board macro and includes the shared
sources; nothing is copied or patched per keyboard.

| keyboard | keys | thumbs/side | adapter | why it differs |
|---|---|---|---|---|
| corne (CRKBD) | 36 | 3 | `config/corne.keymap` | 5-column build; selects upstream's `foostan_corne_5col_layout` |
| tempest | 36 | 3 | `config/tempest.keymap` | local shield |
| seppelit | 36 | 3 | `config/seppelit.keymap` | local shield |
| sweep (cradio) | 34 | 2 | `config/sweep.keymap` | two thumb keys fewer |

Shared key positions are written as **zmk-helpers labels** (`LT4`, `LM0`,
`LH0`, …) rather than numbers. Each board's `key-labels` header (`36.h` or
`34.h`) resolves those labels to its own numbering, so one combo definition is
automatically correct on every board. This is what replaces the old
`generate_keymaps.sh`, which replicated the keymap three times and patched
`key-positions` with `grep`/`sed` — a process that failed *silently* whenever a
position was mistyped, because a combo on the wrong keys still compiles.

## Leader key: symbols, emoji and text snippets

The leader key carries far more than the sign-off snippets it started with.
Press it, then a short sequence:

| what | how | example |
|---|---|---|
| **math symbols** | leader, `M`, then the symbol's name | `M S U M` → ∑, `M L T E Q DOT` → ≤ |
| **emoji** | leader, `E`, then the name | `E H E A R T` → ❤, `E T H U M B U P` → 👍 |
| **Greek** | leader, `G`, then one letter | `G G` → γ, `G G`+Shift → Γ |
| **sign-offs** | leader, two or three letters | `O B R` → "Obrigado,\nHeiko" |
| **unicode mode** | leader, `U X L/W/M` | switch the input method to Linux+Android/Windows/macOS |

### Unicode input needs a host-side helper

Every symbol, emoji, Greek letter, ACCENT mark and the ß chord is typed by
entering a code point, and each OS does that differently. The mode is switched
with `leader` `U X L` / `U X W` / `U X M`, and **Windows is the boot default**.

| mode | needs | can reach |
|---|---|---|
| `UXW` Windows | [WinCompose](https://github.com/ell1010/wincompose) installed | everything |
| `UXL` Linux / Android | an input method (fcitx5) | everything |
| `UXM` macOS | nothing | everything |

On Linux and Android the mode is the Linux one: `Ctrl`+`Shift`+`U`, then the
hex digits, then `Space` (`UC_MODE_LINUX`). The modifier is tapped and released
first - fcitx5 does not need it held while the digits are typed.

**Windows requires WinCompose.** Without it the keyboard still sends the
sequence but nothing appears - for *any* symbol, not just some. Install it and
it runs at startup. If you prefer no extra software, `UC_MODE_WIN_ALT`
(HexNumpad) works out of the box but cannot reach code points above U+FFFF,
which excludes most emoji.

### ß is C+V, and it is a code point now

**C+V on QWERTY types ß**, and **Shift+C+V types ẞ** (U+1E9E, capital sharp S).
The chord is unchanged; what it sends is not. It used to send the pt_PT
`AltGr`+`S` key, which only works where the host layout defines that key:

* **Linux** is fine - the pt_PT layout has ß on `AltGr`+`S`.
* **Windows 11** was not: the raw chord did not reliably produce ß there.
* **Android** was worse: there is no pt_PT `AltGr`+`S` at all, so no native key
  combination can produce ß. The chord did nothing.

So the board now sends the code point **U+00DF** through the same unicode path
as every other symbol, and the host helper types it. That makes the chord behave
identically on all three platforms, at the cost of requiring the helper:

| platform | what ß needs |
|---|---|
| Windows 11 | WinCompose installed (`UXW`, the boot default) |
| Linux | fcitx5 (`UXL`) |
| Android | Fcitx5 for Android installed and selected as the active IME |

The Android entry matters more than it looks: Gboard ships as the default IME on
most Android devices, and Fcitx5 does nothing until it is explicitly selected.

Android uses the same Linux unicode mode as Linux, so `UXL` is the mode
for both. Switching is per connected machine: the BLUETH layer profile keys set
the profile and the mode together (`#0` Windows, `#1`-`#4` Linux), and
`leader` `U X L/W/M` overrides the mode by hand. See
[config/include/combos.dtsi](config/include/combos.dtsi) for the binding and
`bt_win`/`bt_linux*` in `config/include/macros.dtsi` for the profile macros.

### The vector arrows and harpoons never attach to the letter

The five arrow/harpoon marks on the ACCENT layer (`←  →  ↔  ⃐  ⃑`) do not merge
with the preceding character, on any OS. That is Unicode, not the keyboard:
unlike `e` + acute, which folds into one precomposed character, arrows and
harpoons have **no precomposed form anywhere**, so there is nothing to fold
into. Whether they render stacked over the letter or beside it depends on the
application and font. Word and most LaTeX editors handle them; plain text
fields often do not.

Names follow **typst/LaTeX** and are never renamed: `sum`, `approx`, `and`,
`arrow.r`. Dots inside a name are dropped, so `arrow.cm` is `M A R R O W C M`.

Where a name is the start of a longer one, a **DOT goes on the end**: `and` is
`M A N D DOT` and `lt.eq` is `M L T E Q DOT`, because `and.big`, `lt.eq.slant`
and others also exist. If you type the short form and nothing appears, the
leader is still live - add the DOT. Trying `M S U M` and getting ∑ with no DOT,
then `M L T E Q` and getting nothing, is the intended way to discover it.

Greek is **not** under `M` at all - it has its own prefix, so `leader` `G` `G`
gives γ and the same with Shift gives Γ. See the Greek row above.

[docs/LEADER-SYMBOLS.md](docs/LEADER-SYMBOLS.md) lists the exact sequence for
every entry, active or disabled.

**500 math symbols and 451 emoji are active.** The cap is a RAM budget, not a
limit on what is reachable: the leader sequences live in RAM (the module declares
them `static` but not `const`), at 144 bytes each, so ~1000 sequences is what
fits alongside ZMK's BLE and Studio. Roughly 500 more math symbols and 900 more
emoji are present but commented out in the generated files. The full list, with
each symbol's glyph and status, is in
[docs/LEADER-SYMBOLS.md](docs/LEADER-SYMBOLS.md), which links the
[math](docs/LEADER-MATH.md) and [emoji](docs/LEADER-EMOJI.md) tables.

Where a typst name collides with another, the **LaTeX command** is used instead
— `lt.eq` is `LEQ`, `union.big` is `BIGCUP`, `arrow.r.double` is `RIGHTARROW` —
because that is what a maths user already types.

Note the leader sequences are **not drawn** in the keymap SVGs: at this size
they would paginate into hundreds of virtual layers. The markdown reference
above is the documentation.

### Choosing which symbols are enabled

```sh
just symbols              # math,  http://127.0.0.1:8000
just symbols emoji        # emoji
```

Serves a local page listing every candidate — enabled and disabled — with its
glyph, typst name and leader sequence, and a toggle per row. A live counter
shows the RAM the current selection costs and warns past the size known to link.
Nothing is written until **Submit**, which comments the chosen lines in or out
of the `.dtsi` and exits. Ctrl-C leaves the files untouched.

There is no separate state file: **the `.dtsi` is the source of truth.** The tool
reads the enabled set from it, and the generator reads it back, so triage
choices survive regeneration and a new upstream typst symbol arrives disabled.

### Regenerating

```sh
just symbols-docs         # rewrite docs/LEADER-*.md from the .dtsi files
just symbols-gen          # pull new symbols from typst, then rewrite everything
```

`symbols-docs` reads only `config/include/leader-*.dtsi`, so it needs no network
and changes no code. A CI job runs it on every change to those files and commits
the result, which is what keeps the tables below the code rather than beside it.

`symbols-gen` re-fetches typst's tables. The enabled set is preserved, so it is
only needed to pick up new symbols upstream.

## Using a conventional keyboard (keyd)

When the split board stays at home, `keyd/` carries the same layout onto any
conventional 6-row pt_PT keyboard — a laptop's internal one or an external
one. keyd has no thumb cluster, so the six thumb behaviours are relocated to
CapsLock (leader), Tab (NUMNAV), right AltGr (SYMBOL) and Backspace;
`key_repeat`, the MOUSE layer and the BLUETH layer are dropped because keyd
cannot express them. The config targets a pt_PT keymap; the vendor special keys
(mic mute, wifi, bluetooth, keyboard backlight) are bound only where the keyboard
actually has them.

* [docs/KEYD-GUIDE.md](docs/KEYD-GUIDE.md) — how to install it and reach each
  feature; what is and is not possible.
* [docs/KEYD-ANALYSIS.md](docs/KEYD-ANALYSIS.md) — the design reasoning and the
  keyd/ZMK differences that matter.
* [docs/KEYD-VERIFICATION.md](docs/KEYD-VERIFICATION.md) — adversarial review,
  with the six defects it found and how each was fixed.

`keyd/pt_pt.conf` is generated — do not edit it by hand:

```sh
python3 keyd/tools/gen_pt_pt.py          # regenerate from the ZMK sources
python3 keyd/tools/gen_pt_pt.py --check  # fail if the file is stale
python3 keyd/tools/audit.py              # checks keyd check does not do
```

## Repository layout

```
config/
  include/keys.h          board selection, PT keycodes, layer indices, timing
  include/behaviors.dtsi  hold-taps (&hm/&hms/&urm/&skm), sticky layers, leaders
  include/macros.dtsi     the ZMK_MACRO definitions
  include/combos.dtsi     all combos, in key labels
  include/layers.dtsi     all 12 layers, via ZMK_LAYER_NAMED
  include/leader-math.dtsi   GENERATED: math symbol leader sequences
  include/leader-emoji.dtsi  GENERATED: emoji leader sequences
  corne.keymap            \
  tempest.keymap           |  thin adapters: board macro + includes
  seppelit.keymap          |
  sweep.keymap            /
  *.json                  keymap-drawer physical layouts
scripts/check_macro_nesting.py  devicetree nesting guard
scripts/gen_leader_symbols.py   regenerates the leader .dtsi files and docs
scripts/triage_symbols.py       web page for choosing which symbols are enabled
zmk_macro_gen.py                turns typed text into a ZMK_MACRO block
docs/LEADER-SYMBOLS.md          the leader symbol reference index (generated)
docs/LEADER-MATH.md             math symbol table (generated)
docs/LEADER-EMOJI.md            emoji table (generated)
```

`config/zmk-helpers` is a symlink into the `zmk-helpers` submodule, pinned to
upstream `main`.

## Editing the keymap

Edit the shared file for anything that concerns all keyboards:

* a key binding → `config/include/layers.dtsi`
* a combo → `config/include/combos.dtsi`
* a macro → `config/include/macros.dtsi`
* a behaviour or leader sequence → `config/include/behaviors.dtsi`

Only edit a `config/<keyboard>.keymap` adapter if that keyboard needs something
genuinely different. Board-specific divergence is written inline with
`#ifdef ZMK_KB_34` (sweep), as in the thumb rows of `layers.dtsi`. Keep such
divergence rare and commented — it is the one place where the "one layout"
guarantee is suspended.

Two rules worth knowing, both learned the hard way:

1. **Layer order in `layers.dtsi` is load-bearing.** keymap-drawer resolves a
   combo's `layers` property by position, so the order of `ZMK_LAYER_NAMED`
   calls must match the layer-index `#define`s in `keys.h` (QWERTY=0 …
   ACCENT=11).
2. **Layer node names must not collide with those `#define`s.** `ZMK_LAYER`
   token-pastes its argument, so `ZMK_LAYER(QWERTY, …)` with `#define QWERTY 0`
   in scope would emit `layer_0` with display-name `"0"`. That is why
   `keys.h` provides `ZMK_LAYER_NAMED(node, "Display Name", …)`, which keeps
   the node name lowercase and the display name verbatim.

## Building and flashing

`build.yaml` lists all four keyboards, built by
`.github/workflows/build.yml`. Locally, `just build <expr>` filters that file,
e.g. `just build corne`.

Render the drawings locally with `just draw`; it needs `keymap` (keymap-drawer)
on `PATH` and writes only `img/*.svg` (the intermediate YAML goes to a temp
file).

## Keymaps

<details>
  <summary>Tempest (36 keys)</summary>

![Tempest](./img/tempest.svg)
</details>

<details>
  <summary>Corne (5-column CRKBD, 36 keys)</summary>

![Corne](./img/corne.svg)
</details>

<details>
  <summary>Seppelit (36 keys)</summary>

![Seppelit](./img/seppelit.svg)
</details>

<details>
  <summary>Sweep (34 keys)</summary>

![Sweep](./img/sweep.svg)
</details>
