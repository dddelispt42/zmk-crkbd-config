# keyd for the X390 internal keyboard — design brief

This is the analysis behind `keyd/x390.conf`. It records **what carries over, what
cannot, and why**, so the config does not have to be reverse-engineered later.

The target hardware is the internal keyboard of a Lenovo ThinkPad X390 Yoga. It is
used when the split board is left at home, so the goal is *not* a replacement — it
is to keep the highest-value parts of the ZMK layout reachable on a conventional
6-row laptop keyboard with no thumb cluster.

Everything here was checked against the repo and against keyd's own sources, which
are vendored at `.research/keyd-src` (upstream `rvaiya/keyd`, v2.6.0). Claims about
keyd behaviour cite the man page (`docs/keyd.scdoc`) or the source file.

---

## 1. The hardware constraint

The ZMK layout assumes **36 keys in a 3×5+3 split matrix**, and the thumb cluster
carries six behaviours that are structurally unlike the rest:

| ZMK thumb key | behaviour | what it does |
|---|---|---|
| `LH2` | `&leader1` | the leader key: 49 hand-written sequences + 951 generated symbol sequences |
| `LH1` | `&mo NUMNAV` | momentary layer for digits + arrows |
| `LH0` | `&kp BACKSPACE` | plain backspace |
| `RH0` | `&skm MOUSE SPACE` | tap = space, hold = MOUSE layer |
| `RH1` | `&mo SYMBOL` | momentary layer for programming punctuation |
| `RH2` | `&key_repeat` | repeat last keypress |

The X390 keyboard has **no thumb keys at all**. Its bottom row is
`Ctrl Fn Win Alt Space AltGr arrows`, and its physical layout is a standard
PT/ISO-style 6-row matrix. So all six thumb behaviours must either move onto a
non-thumb key or be dropped.

### What this costs, in principle

* **Thumb keys are structurally cheaper than pinky keys.** A layer key on the
  left thumb can be held while both hands type on the layer. Moving `NUMNAV`
  onto `CapsLock` means the left pinky holds the layer while the *same hand*
  types half the digits — so the "one hand holds, both hands type" property is
  lost for every layer key that ends up under a finger of a typing hand.
* **Home-row mods are the expensive part, not the layers.** ZMK's `&hm` with
  `require-prior-idle-ms` and `tap-preferred` flavour is designed so a fast typist
  never triggers a mod. keyd's nearest equivalent is `overloadt`/`lettermod`, whose
  hold resolution is on key *release* and whose timing model is a single global
  timeout — so home-row mods degrade more than layers do. This is why the config
  below is deliberately conservative about them.

---

## 2. keyd capabilities that matter

### 2.1 What keyd has

| capability | keyd construct | verified in |
|---|---|---|
| momentary layer | `layer(name)` / `overload(layer, key)` | `keyd.scdoc` §2.1 |
| one-shot layer | `oneshot(layer)` | §2.1 |
| tap-hold | `overload()`, `overloadt()`, `overloadi()`, `lettermod()` | §2.1 |
| macros | `macro(...)`, `command(...)` | §2.2 |
| **chords** | `key1+key2 = target` in a layer section | §2.4, `config.c` `layer_lookup_chord` |
| layer-scoped chords | chords only match while their layer is active | `keyboard.c` `check_chord_match`: `if (!kbd->layer_state[idx].active) continue;` |
| arbitrary Unicode | raw UTF-8 on the right-hand side, compiled to `<Cancel>`+3 base-36 digits | `macro.c` → `unicode_lookup_index()`; `data/keyd.compose` |
| alternate layouts | `[pt:layout]` section in `layouts/pt` | shipped upstream |
| per-application remapping | `[app:...]` sections | `keyd.scdoc` §2.6 |

### 2.2 Hard limits (verified in source)

* **32 layers maximum** — `src/config.h:15` `#define MAX_LAYERS 32`. The ZMK config
  uses 12, so there is headroom.
* **64 chords per layer** — `src/config.h:105` `struct chord chords[64];`. The ZMK
  config has 41 combos, so this fits in one layer but leaves little room.
* **64 characters per layer name** — `src/config.h:12`.
* **256 entries per macro** — `src/macro.h:24`.
* **One global chord timeout** — `config.c:830` `chord_timeout`. ZMK has a *per-combo*
  timeout (`COMBO_TIMEOUT 50`, `SPLIT_COMBO_TIMEOUT 75`, `LONG_COMBO_TIMEOUT 175`).
  keyd cannot express three different timeouts; the single value must be a
  compromise. **This is the single largest semantic mismatch in the whole mapping.**

### 2.3 Unicode: better than expected

keyd does not need XCompose for arbitrary code points. `unicode.c` builds a
`<Cancel>` + three base-36 key sequence per code point from its own table of
**34,493** characters, and `data/keyd.compose` maps those sequences back to the
character. A macro containing a literal `∑` is compiled into that key sequence.

Coverage of this repo's generated sets, measured against keyd's table:

| set | active sequences | code points keyd can emit | missing |
|---|---|---|---|
| math (`leader-math.dtsi`) | 500 | 495 | 5 |
| emoji (`leader-emoji.dtsi`) | 451 | 444 | 7 |

The 12 missing code points are all Unicode 15/16 additions (e.g. U+1F8BB, U+1FA88)
that predate keyd's table. Everything the ACCENT layer needs — the 26 combining
marks, the 19 vulgar fractions, super/subscripts — is present.

So the *symbols* are not the problem. **Reaching them is**: ZMK types them by
pressing leader, `M`, then a typst name of up to 29 keys. keyd has no sequence
buffer with per-instance prefix resolution — see §3.3.

### 2.3.1 Macro syntax: spaces, not commas

This cost a real bug during development, so it is worth recording. keyd macros
are **space-separated tokens**, not comma-separated arguments:

```conf
# WRONG - strtok(s, " ") treats this as one token "Hello,world"
a = macro(Hello,world)

# RIGHT - the official form (keyd.scdoc, macro2 example)
a = macro(Hello space World)
```

`parse_macro_expression` runs `str_escape` first, then `macro_parse` splits the
result on spaces and walks each token character by character. So a whole word is
one token and types its letters in order. A literal space must be written as the
key name `space`, a newline as `enter`, a tab as `tab`, and a comma as `comma`.

Also important: `str_escape` recognises only `\n`, `\t`, `\\`, `\)` and `\(`.
Writing `\,` for a comma does **not** produce a comma — keyd leaves the
backslash in place and types `\,`. Commas must be their own token.

The generated sign-off macros follow all of this:
`macro(Best space regards comma enter Heiko)`.

### 2.4 Semantic differences to keep in mind

* **keyd layers are fully transparent** (`docs/DESIGN.md`, v2.3.0): a binding not
  found on the active layer falls through to `[main]`. ZMK's `&trans` behaves
  similarly, so layer bodies port cleanly — but there is no "block this key"
  primitive except `noop`, and no `&none` equivalent that also swallows the key.
* **Modifiers apply to all bindings** except those of the active layer's own
  modifier. So `Shift+<layer key>` still shifts; ZMK's mod-morphs that *consume*
  shift (`&num_sup_N2`, `&bspc_del`) must be written as keyd layer variants keyed
  on the modifier, not as morphs.
* **`overload` resolves on press for the hold, on release for the tap** — hence
  keyd's own advice (`examples/home-row-mods.conf`) to use `overloadt` with a
  one-shot shift to avoid shifted-character errors. **Correction:** an earlier
  draft claimed keyd has no prior-idle guard. That was wrong. keyd has
  `overloadi(action1, action2, idle)` (keyd.scdoc:723-733, src/config.c:98) and
  `lettermod(layer, key, idle, hold)`, an alias for
  `overloadi(key, overloadt2(layer, key, hold), idle)`. That is ZMK's
  `require-prior-idle-ms` under another name, so home-row mods ARE reproduced
  faithfully, using ZMK's own timings. See the config's [main] section.
* **No `&key_repeat` primitive.** keyd has no "repeat last key" action; the
  nearest is a `command()` shelling out to a helper, which is not worth it. Dropped.
* **No pointing/scroll layer.** keyd cannot emit relative motion events; the ZMK
  MOUSE layer (`&mmv`, `&mkp`, `&msc`) is not reproducible. Dropped.
* **No BLE/USB switching.** keyd cannot change the laptop's radio state; the
  BLUETH layer's `&bt`, `&out`, `&bootloader` have no meaning. Dropped.

---

## 3. The mapping strategy

### 3.1 Where the thumb behaviours go

The guiding rule: **put the layer keys where the ZMK thumbs would be if the
keyboard had a thumb row** — i.e. under the strongest available fingers near the
bottom centre — and keep the "hold with one hand" property wherever possible.

| ZMK position | behaviour | keyd placement | rationale |
|---|---|---|---|
| `LH2` leader1 | leader key | **`CapsLock`** | The single most important relocation. CapsLock is unused on this layout (the LOCK layer replaces it) and is on the strongest home-row-adjacent position, reachable without looking. ZMK's own `capslock-esc-basic` precedent. |
| `LH1` NUMNAV | momentary layer | **`Tab`** | Tab is next to CapsLock, so the two layer keys sit adjacent as the ZMK thumb keys did. Tab's normal function moves to the SYMBOL layer. |
| `LH0` BACKSPACE | plain key | **`Backspace`** (unchanged) | Already in the same relative place; no change needed. |
| `RH0` MOUSE/SPACE | — | **dropped**, Space stays Space | keyd cannot produce mouse motion; the tap function is kept. |
| `RH1` SYMBOL | momentary layer | **`right AltGr`** | Right AltGr is the one spare key under the right thumb on this keyboard — literally the closest thing to a thumb key. |
| `RH2` key_repeat | — | **dropped** | No keyd primitive. |

The `MOUSE` layer's useful non-pointing keys (the modifier keys and the media
keys) are merged into NUMNAV/SYMBOL rather than kept as a dead layer.

### 3.2 The layer set actually implemented

Of the 12 ZMK layers, these carry over with meaning:

| ZMK layer | idx | keyd layer | status |
|---|---|---|---|
| QWERTY | 0 | `[main]` | implemented (PT layout) |
| NUMNAV | 1 | `numnav` | implemented — digits, arrows, fraction chords |
| SYMBOL | 2 | `symbol` | implemented |
| FUNADJ | 3 | `funadj` | implemented — F1-F12, nav keys |
| ACCENT | 11 | `accent` | implemented — combining marks via Unicode |
| LOCK | 10 | — | dropped (capslock already does this) |
| MOUSE | 4 | — | **not possible** (pointing) |
| MEDIA | 5 | `media` | partly — media keys only |
| WMCFG | 6 | — | dropped (it drives AHK/app shortcuts) |
| MSOUTL | 7 | — | dropped (Outlook-specific macros) |
| MACROS | 8 | — | dropped |
| BLUETH | 9 | — | **not possible** (radio control) |

### 3.3 The leader key — the hard problem

ZMK's `&leader1` is a state machine: it buffers key presses until the buffer
matches a registered sequence, fires that sequence's binding, and times out
otherwise. It resolves **prefix ambiguity per instance** — the repo's own comment
at `behaviors.dtsi:107` records that `<M O>` had to be removed because it was a
prefix of every math name starting with "o" and fired first.

keyd has **no such construct**. It has chords (simultaneous, layer-scoped) and
macros (a fixed action per key). It cannot buffer a variable-length key sequence.

**Therefore the leader key is implemented as a layer plus a generated
tree**, in two parts:

1. **`leader` layer** on CapsLock: pressing CapsLock enters the leader layer. Each
   key on that layer is a *prefix dispatch*, not the final action.
2. **A generated state tree.** A keyd layer has only 256 key slots and 64 chords,
   so a literal 951-leaf tree cannot be spelled out as nested layers within the
   32-layer budget. The practical design is:
   * **hand-written sequences** (sign-offs, Greek, unicode-mode) go directly into
     the `leader` layer as `key = macro(...)` — 49 of them, one key each, matching
     the ZMK two/three-letter mnemonics exactly.
   * **the generated math/emoji sets** are reached via the `M`/`E` prefix keys,
     which switch to `leader_m`/`leader_e` layers where each *first letter* is a
     prefix key. Deeper levels are emitted by the generator script into additional
     layer sections until the key-slot budget is hit.
   * where the tree would exceed the layer budget, the **fallback is the
     direct Unicode sequence**: `<Cancel>`+3 base-36 digits, which keyd emits
     without needing a layer at all. That is a much longer thing to type, so it is
     documented as the escape hatch rather than the primary path.

**Prefix safety must be enforced by the generator**, exactly as ZMK's leader
module enforces it: no binding may be a prefix of another in the same layer. The
ZMK repo hit this bug (`mo` vs `omega`) — the keyd generator must assert it.

### 3.4 Chords replacing combos

keyd chords are layer-scoped, matching ZMK's `layer_mask` gating. Mapping the 41
combos:

* The **19 vulgar fractions** are NUMNAV-only digit pairs in ZMK. keyd's `numnav`
  layer holds digit keys on the top row, so the same two-finger chords port
  directly — and layer scoping makes them safe against layer-0 collisions exactly
  as in ZMK. **This is the highest-fidelity port in the whole config.**
* The **esc/tab/ret/home-row chords** port, but with caveats: keyd's single global
  `chord_timeout` cannot distinguish the 50 ms shortcuts from the 175 ms
  three-finger ones. Set to a value near ZMK's `SPLIT_COMBO_TIMEOUT` (75 ms) as a
  compromise, and document which chords get harder.
* **Three-key chords** (`LM3 LM2 LM1` etc.) are supported by keyd (`config.c`
  rejects more than 4), but are much harder to hit reliably on a laptop keyboard
  whose key spacing differs from the split board. Implement the two-key chords
  and document the rest as omitted.

### 3.5 Unicode compose and modifiers

The ZMK ACCENT layer sends 26 combining marks. keyd ports these directly as
literal characters in macros — **and they arrive as the character, not as a
compose keypress**, because keyd emits the `<Cancel>` sequence internally. So the
combining-mark behaviour is actually *cleaner* in keyd than in ZMK, where the
`&uc` module must guess the OS's input mode.

The one real risk: **GTK4 applications with a large XCompose file are known to
crash** when keyd's `<Cancel>` sequences arrive (`keyd.scdoc`, NOTES). Documented
as a known limitation rather than worked around.

### How the ACCENT layer is entered

ACCENT binds 26 marks to the top two rows — including letters like `a`, `s`, `f`,
`g`, `h`. That looks like a conflict with typing, but it is not: ACCENT is
reached by a **one-shot** from the SYMBOL layer (`backslash = oneshot(accent)`),
and keyd's one-shot layer stays active for exactly one subsequent keypress
(`keyboard.c`, `OP_ONESHOT*`). The order is therefore:

1. type the base character on `[main]` — ordinary typing, ACCENT not involved;
2. hold right AltGr, tap `\` — ACCENT becomes active for one key;
3. press the mark key — the mark is emitted and ACCENT deactivates.

Because the mark key is pressed *after* the base character, the two never
compete for the same press. This is the same ordering ZMK's ACCENT layer uses.

---

## 4. Honest coverage summary

| ZMK feature | reachable in keyd? | fidelity |
|---|---|---|
| 12 layers | 6–7 implemented | good for NUMNAV/SYMBOL/FUNADJ/ACCENT |
| home-row mods | `lettermod()` | good — ZMK's prior-idle guard under another name |
| upper-row layer-mods (`&urm`) | approximated via `overload` | good |
| 41 combos | ~20 implemented | good for fractions, fair for 2-key |
| 49 leader1 hand-written sequences | yes | exact mnemonics |
| 26 Greek leader sequences | yes | exact |
| 500 math + 451 emoji | generated tree or direct Unicode | **partial** — layer budget |
| 47 macros | ~15 ported | the app-specific ones dropped |
| MOUSE layer | no | impossible in keyd |
| BLUETH layer | no | impossible in keyd |
| `&key_repeat` | no | no keyd primitive |
| PT layout | yes, in keyd | exact (`layouts/pt`) |
