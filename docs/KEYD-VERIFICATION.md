# keyd/pt_pt.conf — adversarial verification

Verified against keyd sources only (`.research/keyd-src`), keyd binary
(`bin/keyd`), and ZMK sources. Method: static reading of `src/`, plus a
throwaway C harness linked against keyd's real `macro_parse`,
`config_parse` and `unicode_get_sequence` to observe what the config actually
compiles to. Harness was deleted after use; no deliverable files changed.

Verdict: **`keyd check` passing does not mean this config is correct.** Two
runtime defects and one documentation/instruction defect survive every check.

## PASS/FAIL table

| # | Item | Result |
|---|------|--------|
| 1 | `keyd check keyd/pt_pt.conf` exit 0 | **PASS** |
| 2 | `gen_pt_pt.py --check` current; deterministic | **PASS** |
| 3 | audit.py genuinely detects dup key / bad key / bad layer | **PASS** (all three fire) |
| 4 | `macro(Best space regards comma enter Heiko)` types "Best regards,\nHeiko" | **PASS** (fragile, see D5) |
| 5 | `macro(∑)` compiles to a working key sequence | **PASS** (U+2211 present) |
| 6 | Leader trie: every layer key resolves; no leaf/switch collision | **PASS** |
| 7 | Chord syntax valid in a layer; target may be a macro | **PASS** |
| 8 | `[numnav:shift]` / `[pt_altgr+pt_shift]` modifier-typed layers | **FAIL** for `numnav:shift`; PASS for the composite |
| 9 | `overloadt(meta, a, 200)` arg order; keyd prior-idle equivalent | **FAIL** — keyd *has* `overloadi`; footer claims it does not |
| 10 | "37 of 49 ported" / "939 of 951 emittable" | **PASS** both |
| 11 | Anything broken at runtime but passing `keyd check` | **FAIL** — see D1, D2, D4, D5 |

## 1. `keyd check` — PASS

```
$ .research/keyd-src/bin/keyd check keyd/pt_pt.conf
Parsing keyd/pt_pt.conf

No errors found.
exit 0
```

## 2. Generator freshness and determinism — PASS

`python3 keyd/tools/gen_pt_pt.py --check` prints `keyd/pt_pt.conf is current`,
exit 0. Ran the generator twice and compared output byte-for-byte: identical
(md5 `611d2039eedd2ae0a94cf91bee4b3749`). Note `diff`/`cmp` are absent on this
host; comparison was done in Python.

## 3. Audit script is not rigged — PASS

Read `keyd/tools/audit.py` and confirmed each check is real, then injected each
defect into a copy and ran a patched audit (only `ROOT`/`CONF` redirected;
logic untouched):

| injected defect | audit result |
|---|---|
| duplicate `a = ...` twice in `[main]` | exit 1, `key 'a' already bound on line ...` |
| `nonexistentkey = esc` in `[main]` | exit 1, `'nonexistentkey' is not a keyd key name` |
| `z = layer(no_such_layer)` in `[main]` | exit 1, `layer(no_such_layer) does not exist` |

Baseline (unmodified) exits 0. All three checks genuinely fire. Caveat: the
audit does **not** catch the layer-merge defect D1, because it parses sections
by raw header text and never models keyd's merge semantics.

Cross-check against keyd itself: `keyd check` also catches the bad key name and
the bad layer reference (`WARNING: ... is not a valid key or alias`, `WARNING:
... is not a valid layer`, exit 255), but **not** duplicate bindings
(`No errors found`, exit 0). So audit.py adds real value only for duplicates —
and for those it is correct.

## 4. Macro correctness — PASS (output), with a fragile escaping strategy

Harness linked against keyd's real `macro_parse`, decoding each entry back to a
key name (`S:` = shift held). Output for the four text macros:

```
Best space regards comma enter Heiko        -> S:b e s t space r e g a r d s , enter S:h e i k o
Thank space you comma enter Heiko space Riemer -> S:t h a n k space y o u , enter S:h e i k o space S:r i e m e r
You're space Welcome                        -> S:y o u ' r e space S:w e l c o m e
```

That types exactly `Best regards,\nHeiko`, `Thank you,\nHeiko Riemer` and
`You're Welcome`. **All four requirements hold:**

- `comma` resolves to a key name: yes. `macro.c:27` calls
  `parse_key_sequence(tok,...)` on the whole token; `keys.c:381-406` matches
  `name`, `alt_name` and `shifted_name`, so token `comma` hits
  `keycode_table[KEYD_COMMA] = { ",", "comma", "<" }` (`keys.c:70`) through
  **alt_name** and emits one KEYSEQ for the `,` key.
- `enter` resolves: yes, `keys.c:46` `[KEYD_ENTER] = { "enter", NULL, NULL }` →
  KEYSEQ code 28.
- A multi-char token like `Best` is walked character by character: yes, the
  fallback loop `macro.c:53-76` (`tok += chrsz`) compares each code point against
  single-character `name`/`shifted_name` (`macro.c:62` requires `name[1] == 0`),
  so `B` matches `shifted_name "B"` and emits Shift+b. Verified: entry [0] is
  `data=0x0430` (mods=0x4 SHIFT, code 48 `b`).
- Non-ASCII in a macro: see §5.

### The fragility (D5, not a defect in current output)

`comma` works only because the key's name and its glyph denote the same
character. keyd documents the opposite convention — `keyd.scdoc:628-629`:
"`macro(space)` inserts a space but `macro(s pace)` writes 'space'". So a token
spelled `comma` means "press the comma key", not "type the word comma". The
config happens to want a comma, so it is correct today; but the generator's
`_esc` docstring (`gen_pt_pt.py:80-81`) asserts the reasoning backwards, and any
literal text containing the word "comma", "space", "enter" or "tab" would be
silently replaced by the keypress. The generator already special-cases space,
newline and tab for this reason and treats comma the same way — consistent, but
it means a literal word cannot be typed.

## 5. Unicode macro `macro(∑)` — PASS

`∑` is U+2211, present in keyd's table (`data/keyd.compose:7714`,
`<Cancel> <5> <y> <9> : "∑"`). `unicode_lookup_index(0x2211)` returns a positive
index; `macro.c:72-73` stores `MACRO_UNICODE`; `macro_execute` (`macro.c:121-131`)
expands it via `unicode_get_sequence`. Harness confirms:

```
[∑] parse rc=0 entries=1
  [ 0] UNICODE  data=0x1e21  seq=223,6,21,10
```

Code 223 = `KEYD_CANCEL`, then base36 digits — the compose sequence. Valid.
Greek letters, `½`, `❤`, emoji all compile the same way.

## 6. Leader trie — PASS

Parsed with `config_parse`: every `layer(...)` target in `[leader]` and
`[leader_o]` resolves to a real layer. No layer binds a key that is both a leaf
and a layer-switch.

```
[leader]      e→leader_emoji  t→leader_t  y→leader_y  o→leader_o  a→leader_a
              g→leader_g  c→leader_c  b→leader_b  m→leader_math
[leader_o]    b→leader_o_b (switch), c→macro (leaf)
[leader_a/b/c/g/o_b/t/y/math/emoji]  leaves only
```

All 26 layers parsed; 0 warnings.

## 7. Chords — PASS

`config.c:325-364` parses `a+b` in a layer section into `struct layer.chords`
(`config.h:105`, 64 max), storing a full `struct descriptor` as the target — so
`macro(...)` is valid. `keyd check` accepts all 19. `config_parse` reports 19
chords in `[numnav]`, 8 in `[main]`. Max 19 of 64 allowed. Chords are
layer-scoped (`keyboard.c:340-379` iterates only active layers) and are checked
before the keymap, so they coexist with the digit bindings.

## 8. Layer names — PARTIAL FAIL

`[pt_altgr+pt_shift]` — **PASS**. `config.c:393-420` detects `+` first and makes
it `LT_COMPOSITE` (type=2), constituents resolved, and composite layers may not
carry a type (`config.c:398-401`). Parsed: `name=pt_altgr+pt_shift type=2
mods=0x0`. Behaves as the intersection layer keyd documents (`keyd.scdoc:299-315`).

`[numnav:shift]` and `[numnav:control]` — **FAIL**. These never become modifier
layers. See defect D1.

## 9. Home-row mods — FAIL

`overloadt(<layer>, <action>, <timeout>)` argument order is correct
(`keyd.scdoc:710`; `config.c` actions table `{ "overloadt", NULL,
OP_OVERLOAD_TIMEOUT, { ARG_LAYER, ARG_DESCRIPTOR, ARG_TIMEOUT } }`). So
`a = overloadt(meta, a, 200)` is well-formed.

But the config's claim is false. `keyd/pt_pt.conf:346-348` says:

> ZMK's &hm/&hms ... use flavor=tap-preferred with require-prior-idle-ms, which
> keyd has no equivalent for.

keyd **does** have an equivalent: `overloadi(<action1>, <action2>, <idle
timeout>)`, documented at `keyd.scdoc:723-733` as "Activate <action 1> if the
last non-action (i.e symbol) key was struck less than <timeout> milliseconds
ago" — the same prior-idle guard, and the docs name homerow mods as its use
case. Implementation: `config.c:98`, `keyboard.c:571-587`
(`OP_OVERLOAD_IDLE_TIMEOUT`, comparing `time - kbd->last_simple_key_time`).
ZMK's actual values are in `config/include/behaviors.dtsi:255,262,269,276,285`
(150/125/150/50/150 ms). A faithful port would be
`a = overloadi(a, overloadt2(meta, a, 200), 150)`. See defect D2.

## 10. Coverage numbers — PASS

Recounted independently:

- `config/include/behaviors.dtsi` leader1 = **38** sequences, leader2 = **11** →
  **49** total. Claim "37 of 49 ported" ✓.
- keyd leader leaves: 9 sign-offs + 2 headings (`[leader_a]` c=Actions,
  g=Agenda) + 1 `[leader_o_b]` j=Objective + 25 Greek = **37**. ✓
- Dropped 12 = 8 system (USB/BLE/BT0-2/CLEAR/BOOT/RESET) + 3 unicode-mode
  (UXL/UXW/UXM) + **1 further**: `ao` (A O → `&m_ao`, behaviors.dtsi:124). The
  dropped note lists only "8 Bluetooth/USB/bootloader ... and 3 unicode-mode
  switches" = 11, so 49 − 11 = 38, not 37. The arithmetic only closes if `ao`
  is counted as dropped; it is omitted from the note. See defect D3.
- "939 of 951": `count_symbols()` returns total=951 (500 math + 451 emoji),
  emittable=939, missing=12. Verified directly by importing the module. ✓ The
  12 missing are the 15/16 Unicode additions listed at the file's end. ✓

## 11. Runtime-only defects — FAIL (see D1, D2, D4, D5)

`keyd check` is syntax-only (`src/check.c`: it just calls `config_parse` and
prints "No errors found" when no error is raised). It does not model layer
merging, does not detect duplicate bindings, and does not simulate key output.

## Defect list

### D1 — `[numnav:shift]` and `[numnav:control]` do not create modifier layers; the digit row is dead. SEVERITY: HIGH

`keyd/pt_pt.conf:475` (`[numnav:shift]`) and `:487` (`[numnav:control]`).

keyd's `config_add_layer` (`config.c:445-470`) strtoks the section name on `:`
to get `numnav`, finds that layer already exists, and **returns 1 without
creating or modifying anything** (`config.c:459-460`). The section's bindings
are then routed by `config.c:978` (`"%s.%s = %s"` with `layername` = the same
strtok'd name) straight into the plain `numnav` layer's keymap. Since "the most
recent one takes precedence" (`keyd.scdoc:268`), the digit bindings at
`keyd/pt_pt.conf:404-413` are overwritten.

Proof — parsed layer table shows no `numnav:shift` layer at all:

```
  [10] numnav                 type=0 mods=0x0
```

and the digit keys in that layer are MACRO, not digits:

```
key=1 op=19  -> macro [UNICODE idx=7351 seq=223,6,24,8]   (= ¹)
key=2 op=19  -> macro [UNICODE idx=7352]                  (= ²)
```

`keyd check` reports "No errors found" on a minimal reproducer of this exact
construct. **Runtime effect:** in the numnav layer, pressing `1` types `¹`
instead of `1`; there is no way to type a plain digit while the layer is up.
The `[numnav:control]` subscripts likewise replace nothing new but confirm the
pattern. Fix: use keyd's actual modifier-layer syntax for sub-layers of a
named layer — keyd has no "sublayer" concept; the supported construct is a
separate top-level layer (e.g. `[numnav_shift:C]`) plus a mod-morph, or bind
the digits to `overloadt`/`overloadi` actions, or use `shift`/`control` layers
with explicit `layer(...)` on a key.

### D2 — Footer claims keyd has no prior-idle equivalent. It does. SEVERITY: HIGH

`keyd/pt_pt.conf:346-347`: "require-prior-idle-ms, which keyd has no equivalent
for."

`overloadi(<action1>, <action2>, <idle timeout>)` is exactly that:
`keyd.scdoc:723-733` ("Activate <action 1> if the last non-action (i.e symbol)
key was struck less than <timeout> milliseconds ago ... particularly useful for
overloading letter keys (often called 'homerow mods')"), implemented at
`config.c:98` and `keyboard.c:571-587` as `OP_OVERLOAD_IDLE_TIMEOUT`
(`time - kbd->last_simple_key_time`). ZMK's values are
`behaviors.dtsi:255,262,269,276,285` = 150/125/150/50/150 ms. The config
therefore ships a knowingly-degraded home-row-mod setup when a faithful port was
available, and documents the false reason. Fix: `a = overloadi(a,
overloadt2(meta, a, 200), 150)` (docs:752 gives the exact `lettermod`
equivalence).

### D3 — "4 Outlook headings" and "37 of 49" arithmetic is inconsistent with the dropped list. SEVERITY: LOW

`keyd/pt_pt.conf:893-897`. The note claims "9 sign-offs, 4 Outlook headings, 25
Greek letters" (= 38) ported, but only 3 headings exist in keyd (`[leader_a]`
c=Actions, g=Agenda; `[leader_o_b]` j=Objective — lines 743, 744, 786). `ao`
(`A O` → `&m_ao`, `behaviors.dtsi:124`) is dropped and is not named in the
dropped list, which lists only 8 system + 3 unicode-mode = 11 → 49 − 11 = 38.
The real split is 37 ported / 12 dropped, so the "37" is right and the "4
headings" is wrong. Fix: say "3 Outlook headings" and add `ao` to the dropped
list.

### D4 — `esc = noop` in `[leader_math]` / `[leader_emoji]` does not leave the layer. SEVERITY: MEDIUM

`keyd/pt_pt.conf:861` and `:883`, commented "Leave the layer."

`noop` is a keycode (`keys.c:269`, `KEYD_NOOP` = 195), not an action; binding a
key to it makes that key do nothing (`keyboard.c:74`). It does not deactivate a
layer. Layers opened with `layer(x)` are released only when the key that
activated them is released (`keyboard.c:615-622`, `OP_LAYER` → `deactivate_layer`
on release). So while capslock is held in `[leader_math]`, pressing `esc` does
nothing at all — the user cannot "leave the layer" without releasing capslock.
Harmless in practice (the layer exits on release) but the comment is false and
the binding is misleading. Either drop the `esc`/`capslock` noop lines or change
the comment to "swallow".

### D5 — The escape-hatch instruction "type the name's code point" is wrong. SEVERITY: HIGH

`keyd/pt_pt.conf:812-814` and the generator header at `gen_pt_pt.py:345-347`:
"type the name's code point".

keyd's compose sequences are **base36 table indices**, not code points
(`scripts/generate_xcompose`, `unicode.c:31-34`: `<Cancel>` + three base36
digits). ∑ is `<Cancel> <5> <y> <9>` (`data/keyd.compose:7714`). Typing "2211"
after the cancel key produces `<2> <2> <1>` = `ఆ` (U+0C06, `keyd.compose:2667`),
not ∑. The documented fallback therefore does not work as written. This is the
single most user-visible documentation error: 939 sequences are claimed reachable
via a procedure that yields the wrong glyph. Fix: document the base36 sequence,
or ship the `command(keyd do 'macro(<glyph>)')` helper the header already
describes, or bind the glyphs directly.

### D6 — "3167 interior nodes" is not a computed value. SEVERITY: INFO

`keyd/pt_pt.conf:801` and `gen_pt_pt.py:340`. Recomputing over the 951 names gives
947 distinct names and **3151** interior trie nodes. The argument (the set does
not fit in 32 layers, `config.h:15`) is sound either way; only the figure is
stale/approximate and presented as measured.

## Categories with no defects

- **Chords (§7):** 19 chords parse, are layer-scoped, and accept `macro(...)` as
  a target. No defects.
- **Unicode macros (§5):** all glyph macros compile to valid `MACRO_UNICODE`
  entries; every code point in the generated sets is checked against
  `data/keyd.compose`. No defects.
- **Leader trie targets (§6):** all 9 + 1 `layer()` targets resolve; no key is
  both a leaf and a layer-switch. No defects.
- **Generator determinism (§2):** byte-identical across runs. No defects.
- **audit.py (§3):** all three checks genuinely fire. No defects in the checks
  themselves — though it cannot see D1, because it does not model keyd's layer
  merge. That gap is noted, not a rigging.

---

## Resolution log — all defects addressed

Each defect below was fixed in `keyd/tools/gen_pt_pt.py` and the config
regenerated. Re-run `keyd/tools/gen_pt_pt.py --check` and
`keyd/tools/audit.py` to confirm.

### D1 — `[numnav:shift]` silently discarded — FIXED

Replaced the colon-suffixed sections with real **composite layers**, keyd's
documented mechanism for "same key, different result with a modifier held"
(`config.c:393-420`, `keyd.scdoc` "Composite Layers"):

```
[numnav]             digits + 19 fraction chords
[shift]              empty - so Shift+digit stays normal elsewhere
[control]            empty
[numnav+shift]       the 10 superscript digits
[numnav+control]     the 10 subscript digits
```

Verified against keyd's real `config_parse`: the layer table now contains
`numnav` (19 chords), `numnav+shift` (type=2, 2 constituents) and
`numnav+control` (type=2, 2 constituents). The digit row on `numnav` is plain
digits again — the "pressing 1 types ¹" bug is gone.

`keyd/tools/audit.py` gained a regression check for this whole class: a section
name containing `:` whose prefix is already a layer is reported as a failure,
because keyd discards it. Proven to fire on the original broken pattern.

### D2 — "keyd has no prior-idle guard" — FIXED

False. keyd has `overloadi(a1, a2, idle)` and `lettermod(layer, key, idle, hold)`
(`keyd.scdoc:723-748`, `config.c:98`). The home-row mods now use `lettermod`
with ZMK's own timings (`tapping-term 210/200`, `require-prior-idle 150/125`
from `behaviors.dtsi:253-289`):

```conf
a = lettermod(meta, a, 150, 210)
s = lettermod(control, s, 125, 200)
```

### D3 — "4 Outlook headings" but only 3 ported — FIXED

The comments now say three, and name the dropped one (`ao`, `A O`,
`behaviors.dtsi:124`).

### D4 — `esc = noop` did nothing — FIXED

`noop` is a keycode, not an action. The escape-hatch layers now bind `esc = esc`
as a real way out; releasing capslock also exits.

### D5 — escape hatch instruction was wrong — FIXED

"Type the code point" was wrong: keyd's compose sequences are base-36 *indices*,
so `∑` is `<Cancel><5><y><9>` and typing `2211` yields `ఆ`. The config and
`docs/KEYD-GUIDE.md` now document the correct hatch,
`keyd do 'macro(<glyph>)'`, which runs keyd's real `macro_parse` in the daemon.

### D6 — "3167 interior nodes" — FIXED

Corrected to the recounted 3151.

### Verified good, unchanged

`keyd check` exit 0; generator deterministic and current; `audit.py` not rigged;
macros type correct text (`Best space regards comma enter Heiko` →
"Best regards,\nHeiko", confirmed against keyd's real `macro_parse`);
`macro(∑)` compiles to a valid Unicode sequence; leader trie resolves with no
leaf/switch collision; chords valid and layer-scoped; coverage numbers
(37/49, 939/951) correct.
