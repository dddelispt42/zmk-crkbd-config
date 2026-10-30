# Improvement backlog

A review of the refactored config, written after the inclusion-based restructure.
Everything here was checked against the repo rather than recalled, and each item
says what it costs and what it risks.

Ordering is by my own judgement of value, not by category. Items marked
**verified** were confirmed by reading the files; items marked **needs a build**
cannot be settled without compiling, because there is no `west`/`cmake` in the
environment this review was done in.

---

## 1. Make the local shields ZMK Studio compatible — **needs a build**

**This is the most consequential item.** You said you use or plan to use ZMK
Studio, and two of the four boards currently cannot.

Both local shields use the legacy matrix transform:

```dts
/* boards/shields/tempest/tempest.dtsi:13,17 */
chosen { zmk,matrix_transform = &default_transform; };
default_transform: keymap_transform_0 { compatible = "zmk,matrix-transform"; ... };
```

ZMK's `physical_layouts.c` computes:

```c
USE_PHY_LAYOUTS = DT_HAS_COMPAT_STATUS_OKAY(zmk_physical_layout)
                  && !DT_HAS_CHOSEN(zmk,matrix_transform)
```

and then asserts:

```c
BUILD_ASSERT(!IS_ENABLED(CONFIG_ZMK_STUDIO) || USE_PHY_LAYOUTS,
    "ISSUE FOUND: Keyboards require additional configuration to allow for "
    "firmware with ZMK Studio enabled...");
```

Because `zmk,matrix_transform` is set, `USE_PHY_LAYOUTS` is false, so **enabling
`CONFIG_ZMK_STUDIO=y` for tempest or seppelit would fail that assert.** ZMK also
emits `#warning "Ignoring the physical layouts and using the chosen matrix
transform."` in that state.

Corne is already correct — it selects upstream's `foostan_corne_5col_layout`,
which is a real `zmk,physical-layout` carrying a `keys` array, and sets no
`chosen zmk,matrix-transform`.

**Fix:** give each local shield a `zmk,physical-layout` with a `keys` array and a
`transform` phandle, and drop the `chosen zmk,matrix-transform`. Studio also
requires `keys`, so the 36 `key_physical_attrs` entries have to be authored — the
existing `config/*.json` drawing layouts are the natural source for the geometry.

**Note:** `ZMK_KEYMAP_LEN` is the maximum over all layouts, so the existing
36-entry layers stay valid; no keymap change is needed.

**Extra:** the two shields are **byte-identical** (verified: `diff` of
`tempest.dtsi` and `seppelit.dtsi` is empty). Since you now ship four keyboards
from one config, they could share a single common shield `.dtsi` with per-board
overlays — the same deduplication that was applied to the `.conf` files.

---

## 2. Restore the four TODOs lost in the refactor — **verified**

The refactor deleted `config/keymap`, and with it four TODOs that recorded
intended work. They are recoverable from git:

```sh
git show main:config/keymap | grep TODO
```

```
// TODO: add generic mechanism to lock layers
// TODO: add 2x rotary encoder - use Fxx or LANG1/LANG2 as free keycodes for AHK
// TODO: add leader key: move AHK into keyboard to use all all machines - use C_AL_CALC/C_AC_SEARCH/C_AL_CAL
// TODO: add trackball
```

Only `//TODO(heiko): not yet used` on `skm` survives today, and it is now
misleading — `&skm` **is** used on the QWERTY thumb row (verified in
`layers.dtsi`). The TODO is stale and should be dropped.

These are cheap to restore and represent real intent, so they belong in
`config/include/keys.h` or `behaviors.dtsi` rather than being lost.

---

## 3. Adopt the zmk-helpers macros that are still bypassed — **partly verified**

The refactor adopted `ZMK_LAYER`, `ZMK_COMBO` and the unicode module, but a lot
of hand-written devicetree remains. Counts verified in the repo:

| construct | hand-written now | zmk-helpers macro available |
|---|---|---|
| macros | **48** `ZMK_MACRO(...)` (correct — already the macro) | `ZMK_MACRO` ✅ in use |
| hold-taps | **5** raw `compatible = "zmk,behavior-hold-tap"` | `ZMK_HOLD_TAP` |
| mod-morphs | **4** raw `"zmk,behavior-mod-morph"` | `ZMK_MOD_MORPH` |
| caps-word | **1** raw `"zmk,behavior-caps-word"` | `ZMK_CAPS_WORD` |
| leader behaviors | **2** raw `"zmk,behavior-leader-key"` | ⚠️ see below |
| sticky layer | `&sl { release-after-ms = <1500>; };` property override | `ZMK_STICKY_KEY` |

Converting the 5 hold-taps, 4 mod-morphs and 1 caps-word is mechanical and low
risk: each is a direct substitution with the same property list. It removes the
`compatible`/`#binding-cells` boilerplate and makes the file consistent with
`ZMK_MACRO` usage elsewhere in the same directory.

**The leader behaviours are the exception, and `ZMK_LEADER_SEQUENCE` will not
work for you.** Verified: zmk-helpers' macro expands to

```c
leader_sequences {
    compatible = "zmk,leader-sequences";
    leader_sequence_##name { bindings = <...>; key-positions = <...>; };
};
```

but your leaders use urob's **`zmk-leader-key`** module
(`compatible = "zmk,behavior-leader-key"`, `sequence = <...>`). Different driver,
different properties. Adopting `ZMK_LEADER_SEQUENCE` would mean migrating the
leader module, which is a much larger change than it looks.

---

## 4. CI: stop rewriting history and stop redundant runs — **verified**

Three separate issues in `.github/workflows/`:

**a. `amend_commit: true`** (`draw-keymaps.yml:85`) — the upstream draw workflow
amends the commit that produced the files, rewriting published history on every
keymap push.

**b. `leader-yaml` pushes a commit back to the repo** (`draw-keymaps.yml:64-65`).
It was changed from `--amend` + `--force-with-lease` to a plain commit during the
refactor, which is safer, but it still means CI writes to your branch on every
keymap change.

**c. No `concurrency` block and no branch filter on `build.yml`.** Since
`build.yml` is `on: [push, pull_request, workflow_dispatch]`, pushing to a branch
with an open PR runs the full 9-target matrix **twice**. Verified: neither
workflow declares `concurrency`, so nothing cancels the superseded run.

A `concurrency` group keyed on the branch would fix (c) at no cost:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

**d. `img/*.yaml` is still committed by CI.** These are intermediate
`keymap parse` output — `just draw` no longer produces them locally (it uses
`mktemp` and cleans up), but the upstream workflow commits both `.svg` and
`.yaml` via an explicit `file_pattern`. Gitignoring them is **not** an option:
the action runs `git add` under `set -eu`, and a plain `git add` on an ignored
path exits 1, which would fail the draw job. Removing them for good means either
`destination: artifact` or replacing the reusable workflow with an inline job.

---

## 5. Configuration inconsistencies — **verified**

**a. Duplicate keyboard name.** `tempest.conf` and `seppelit.conf` both set
`CONFIG_ZMK_KEYBOARD_NAME="HeiKey"`, making the two indistinguishable when
pairing over Bluetooth.

**b. Dead setting on three boards.** `common.conf` sets
`CONFIG_ZMK_IDLE_SLEEP_TIMEOUT=1200000`, but corne, tempest and seppelit all set
`CONFIG_ZMK_SLEEP=n`, so the timeout has no effect there. ZMK prints a Kconfig
warning about it. Harmless but confusing; either give those boards `SLEEP=y` or
move the timeout into `cradio.conf`, which is the only board that sleeps.

**c. `BTSEL` is now unused.** The BLUETH layer uses the `bt_*` macros, which also
set the unicode mode. The define is kept deliberately (with a comment saying so),
but it is dead code until something needs a plain profile key.

---

## 6. The equivalence harness is not wired into anything — **verified**

`scripts/verify_equivalence.py` is the strongest safety net in the repo: it
compares *expanded behaviour* (preprocessed bindings per layer, resolved
`key-positions` per combo) and would have caught several of the regressions from
the refactor. But nothing runs it — not the Justfile, not CI.

Adding a `just verify` recipe, or a CI step on `config/**` changes, would turn it
from a tool that existed during the refactor into a permanent guard. Given that
this config is long-lived and hand-edited, that seems clearly worth it.

---

## 7. Documentation drift — **verified**

The README was rewritten during the refactor and has already drifted:

- **Line 121** still says `just draw` "writes `img/*.svg` and `img/*.yaml`".
  It no longer writes the YAML; that was changed to a temp file with cleanup.
- **No mention of Greek letters or the unicode module**, which is now a
  significant feature with an OS-dependent setup step (WinCompose on Windows).
- **No mention of the `LEADER1b` pagination**, so a reader seeing that layer in
  the drawings has no explanation for it.

---

## 8. Smaller items, lower value

**a. `corne_left.conf` / `corne_right.conf`** contain only
`CONFIG_ZMK_SPLIT_ROLE_CENTRAL=y` / `=n`. Corne is built from upstream's CRKBD
shield, which already handles the central/peripheral split, so these may be
redundant. Worth confirming, not worth guessing.

**b. `pre-commit` has exactly one active hook** (`zizmor`); everything else is
commented out. A YAML linter would have caught the malformed `build.yaml`
indentation that slipped in during the refactor, and a shell linter would cover
the Justfile recipes.

**c. `generate_leader_yaml.py` is bespoke** (~280 lines) purely because
keymap-drawer cannot discover leader sequences. It is now doing pagination,
which is more logic than when it was written. Worth re-reading before the next
change to it — but there is no obvious way to delete it while
`zmk-leader-key` is in use.

**d. `skm` TODO is stale** (see item 2) — `&skm` is used, so the comment should
go.

**e. `m_ao` uses `&kp LC(LS(L))`** where the other three Outlook macros use the
same. **This is not a bug** — it was verified as consistent across all four and
present in the original config, so it appears to be an intentional Word shortcut.
Recorded here only so it does not get "fixed" by mistake later.

---

## Things that are fine as they are

Worth stating explicitly, because they look like problems and are not:

- **`config/cradio.conf` is named after the shield, not the board.** ZMK loads
  `config/<shield>.conf`, and sweep's shields are `cradio_left`/`cradio_right`.
  Renaming it to `sweep.conf` silently disables every setting on that board —
  which is exactly the regression that was found and fixed during the refactor.
- **`.conf` files cannot `#include` each other.** Kconfig fragments are merged,
  not textually included. The `common.conf` + `EXTRA_CONF_FILE` arrangement is
  the supported mechanism.
- **`&leader1` is on a combo for sweep.** A 34-key board has no `LH2`, and no
  main key is free on any of the 12 layers, so a dedicated chord is the only way
  to keep the leader reachable there.

---

## Suggested order

1. **Studio support for tempest/seppelit** — you asked for it, it is load-bearing
   for a feature you use, and it needs a build to confirm.
2. **Restore the TODOs** — minutes of work, recovers intent.
3. **Wire the harness into CI** — protects everything else on this list.
4. **CI hygiene** (concurrency, `amend_commit`) — removes recurring friction.
5. **Config inconsistencies.**
6. **zmk-helpers macro adoption** for hold-taps/mod-morphs/caps-word — mechanical,
   do it when the config is otherwise quiet.
7. **Documentation.**

Items 1 and 6 both touch code that is still being stabilised in CI, so they are
best done once the current branch is green.
