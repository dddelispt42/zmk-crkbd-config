# Improvement backlog

A review of the refactored config, written after the inclusion-based restructure.
Everything here was checked against the repo rather than recalled, and each item
says what it costs and what it risks.

Ordering is by my own judgement of value, not by category. Items marked
**verified** were confirmed by reading the files; items marked **partly fixed**
have had some of their findings addressed and say which remain.

Completed items are removed rather than kept as a changelog — git history holds
that. What is listed here is only what is still outstanding.

---

## 1. Set up a local firmware build — **not started, needs ~8 GB free**

**This is the highest-value item on the list**, and it is a process fix rather
than a config fix. Every failure during the refactor was only visible after a CI
round-trip of several minutes, and several were things a local build would have
caught in seconds — including a `ZMK_MOD_MORPH` nesting error that
`keymap parse` cannot see and that cost two CI runs to find. Building locally
turns that feedback loop into seconds.

### What is already present on this machine

| tool | status |
|---|---|
| Arch Linux | ✅ |
| `python3` | ✅ 3.14.8 — see the caveat below |
| `just` | ✅ 1.18.4 |
| `pipx` | ✅ 1.18.4 |
| `cmake`, `ninja`, `dtc` | ❌ missing |
| `yq` (go-yq) | ❌ missing — required by `just build` / `just list` |
| `west` | ❌ missing |
| ARM toolchain / Zephyr SDK | ❌ missing |

### Step 1 — host packages

```sh
sudo pacman -S --needed cmake ninja dtc python-pip python-virtualenv go-yq
```

**`go-yq`, not `yq`.** Arch ships two different packages under that name, and
the Justfile needs the mikefarah one: `just build`/`just list` run
`yq -r "<jq expression>" build.yaml`, and the expression uses jq syntax
(`map`, `combinations`, `.include[]`). The other `yq` in `extra` is a Python jq
wrapper with different syntax, and it will fail on that expression.

`python-west` also exists in Arch, but installing `west` via pipx keeps it out
of the system Python.

### Step 2 — west

```sh
pipx install west
```

**Caveat — Python 3.14.** `west` 1.5.0 declares `requires_python: >=3.9`, but
its classifiers stop at **3.13**; 3.14 is untested. If `west` misbehaves, use a
3.13 environment instead:

```sh
sudo pacman -S python313
python3.13 -m venv ~/.venvs/zmk
~/.venvs/zmk/bin/pip install west
# then call ~/.venvs/zmk/bin/west explicitly
```

### Step 3 — Zephyr SDK 0.16.9 (~1 GB download)

CI uses **0.16.9** (it appears in the build log as
`-- Found toolchain: zephyr 0.16.9 (/opt/zephyr-sdk-0.16.9)`). Matching that
version is what makes a local build reproduce CI:

```sh
mkdir -p ~/.local/opt && cd ~/.local/opt
curl -LO https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v0.16.9/zephyr-sdk-0.16.9_linux-x86_64.tar.xz
tar xf zephyr-sdk-0.16.9_linux-x86_64.tar.xz
cd zephyr-sdk-0.16.9 && ./setup.sh -t arm-zephyr-eabi -c
```

`./setup.sh` registers the SDK in `~/.cmake/packages/Zephyr`, so `west build`
finds it without further configuration.

`arm-none-eabi-gcc` from Arch (16.2.0 in `extra`) is *not* a drop-in substitute
— Zephyr would need `ZEPHYR_TOOLCHAIN_VARIANT=gnuarmemb` and it is not what ZMK
tests against. Use the SDK.

### Step 4 — fetch the sources

```sh
just init
```

That runs `west init -l config`, `west update` and `west zephyr-export`, pulling
ZMK, Zephyr and all modules: `zmk-helpers`, `zmk-unicode`, `zmk-leader-key`,
`zmk-auto-layer`, `zmk-locales`, `nice-view-gem`.

### Step 5 — build

```sh
just list                 # show available targets
just build tempest        # or corne, seppelit, sweep, or 'all'
```

Artifacts are copied to `firmware/`. `just clean-all` removes the west tree.

### Disk and a note on the two zmk-helpers sources

Budget roughly **5–8 GB** total (Zephyr plus every module plus the SDK).

There are **two independent sources of `zmk-helpers`**, which is worth knowing:

* `config/zmk-helpers` is a symlink into `config/zmk-helpers-repo`, a git
  **submodule**.
* `config/west.yml` also lists `zmk-helpers` as a west **project**, which
  `west update` fetches to the workspace root.

The two CI workflows differ here, which is easy to trip over:

| workflow | submodules | so `zmk-helpers` comes from |
|---|---|---|
| `build.yml` (via ZMK's reusable workflow) | **not** checked out — the job log shows `submodules: false` | the **west project** |
| `draw-keymaps.yml` | `submodules: recursive` | either; both are present |

So for firmware builds CI relies on the west project, while locally both exist.
If a local build ever picks up a different version than CI — a header mismatch,
or a macro that exists locally but not remotely — this duplication is the first
thing to suspect.

### Why this matters more than the other items

Items 2, 3 and 9 are quality improvements. This one changes how quickly any
future problem is found: it is the difference between a seconds-long local
`just build` and a multi-minute CI round-trip that only exercises the matrix
after a push.

---

## 2. CI: stop rewriting history and stop redundant runs — **verified**

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

## 3. Configuration inconsistencies — **verified**

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

## 4. The equivalence harness is not wired into anything — **verified**

`scripts/verify_equivalence.py` is the strongest safety net in the repo: it
compares *expanded behaviour* (preprocessed bindings per layer, resolved
`key-positions` per combo) and would have caught several of the regressions from
the refactor. But nothing runs it — not the Justfile, not CI.

Adding a `just verify` recipe, or a CI step on `config/**` changes, would turn it
from a tool that existed during the refactor into a permanent guard. Given that
this config is long-lived and hand-edited, that seems clearly worth it.

---

## 5. Documentation drift — **partly fixed**

The stale `just draw` claim has been corrected: the README said the recipe
writes `img/*.yaml`, which stopped being true when it moved to a temp file.
Two gaps remain:

- **No mention of the unicode module or the Greek letters**, now a significant
  feature with OS-dependent setup: WinCompose on Windows, fcitx5's
  `Ctrl+Shift+U` on Linux. There is also a timing subtlety
  (`ZMK_UNICODE_TAP_MS`/`WAIT_MS`) that took real debugging to find.
- **No mention of the `LEADER1b` pagination**, so a reader seeing that layer in
  the drawings has no explanation for it.

---

## 6. Add the math symbols and operators — **verified, not started**

NUMNAV now carries the vulgar fractions and the super/subscripts (19 combos and
20 mod-morphs). The natural next step is the wider math set, which is large:
the `zmk-unicode` module ships **256 mathematical operators**, **79 letterlike
symbols**, **128 misc-mathematical-B**, **112 arrows** and **33 currency
symbols**, all available via `#include <zmk-unicode/keys/blocks/...>`.

Most valuable candidates, with their verified alias names:

**Relations and comparisons** (mostly for code and notes)

| symbol | alias |
|---|---|
| ≈ | `UC_ALMOST_EQUAL_TO` |
| ≠ | `UC_NOT_EQUAL_TO` |
| ≤ | `UC_LESS_THAN_OR_EQUAL_TO` |
| ≥ | `UC_GREATER_THAN_OR_EQUAL_TO` |
| ≡ | `UC_IDENTICAL_TO` |
| ∝ | `UC_PROPORTIONAL_TO` |
| − | `UC_MINUS_SIGN` (true minus U+2212, not hyphen) |
| ± | `UC_PLUS_MINUS_SIGN` — in **latin_1_supplement**, not the operators block |

**Logic and sets** (useful for Python/Rust notes)

| symbol | alias | symbol | alias |
|---|---|---|---|
| ∀ | `UC_FOR_ALL` | ∃ | `UC_THERE_EXISTS` |
| ∈ | `UC_ELEMENT_OF` | ∉ | `UC_NOT_AN_ELEMENT_OF` |
| ⊂ | `UC_SUBSET_OF` | ⊃ | `UC_SUPERSET_OF` |
| ∪ | `UC_UNION` | ∩ | `UC_INTERSECTION` |
| ∅ | `UC_EMPTY_SET` | ∧ | `UC_LOGICAL_AND` |
| ∨ | `UC_LOGICAL_OR` | ∴ | `UC_THEREFORE` |

**Analysis and geometry**

| symbol | alias | symbol | alias |
|---|---|---|---|
| ∞ | `UC_INFINITY` | √ | `UC_SQUARE_ROOT` |
| ∫ | `UC_INTEGRAL` | ∂ | `UC_PARTIAL_DIFFERENTIAL` |
| ∇ | `UC_NABLA` | ∑ | `UC_N_ARY_SUMMATION` |
| ∏ | `UC_N_ARY_PRODUCT` | ∠ | `UC_ANGLE` |
| ∥ | `UC_PARALLEL_TO` | ⟂ | `UC_PERPENDICULAR` (in misc-mathematical-A, not the operators block) |

**Letterlike** (math notation and units)

| symbol | alias | symbol | alias |
|---|---|---|---|
| ℓ | `UC_SCRIPT_SMALL_L` | ℎ | `UC_PLANCK_CONSTANT` |
| ℏ | `UC_PLANCK_CONSTANT_OVER_TWO_PI` | ™ | `UC_TRADE_MARK_SIGN` |
| ℃ | `UC_DEGREE_CELSIUS` | ℉ | `UC_DEGREE_FAHRENHEIT` |
| ℤ | `UC_DOUBLE_STRUCK_CAPITAL_Z` | ℝ | `UC_DOUBLE_STRUCK_CAPITAL_R` |
| ℕ | `UC_DOUBLE_STRUCK_CAPITAL_N` | ℚ | `UC_DOUBLE_STRUCK_CAPITAL_Q` |
| ℂ | `UC_DOUBLE_STRUCK_CAPITAL_C` | ℙ | `UC_DOUBLE_STRUCK_CAPITAL_P` |

### Implementation options, in rough order of cost

**a. Extend what already exists (cheapest).** NUMNAV has 16 free cells: 5 on the
home row, 8 on the bottom row, and 3 on the thumb-row row (which differs by
board, `#ifdef ZMK_KB_34`). A handful of the most-used symbols could go on some
of those, or as `Shift`-variants of keys that are currently `&trans` — the same
mod-morph mechanism already used for the superscripts.

**b. Add the operators to an existing layer.** SYMBOL is the obvious home for
punctuation-like operators, but it is nearly full — only 4 free cells on a
36-key board. Counting `&trans` cells per layer (note these counts include both
`#ifdef ZMK_KB_34` branches, so they slightly overstate the 36-key reality):

| layer | free cells |
|---|---|
| ACCENT | 32 |
| NUMNAV | 19 |
| MEDIA | 13 |
| MOUSE | 10 |
| FUNADJ | 9 |
| WMCFG / MACROS | 8 each |
| SYMBOL | 4 |
| QWERTY, MSOUTL, BLUETH, LOCK | 0 |

So NUMNAV and MEDIA have the most usable room; SYMBOL does not, despite being
the punctuation layer.

**c. A dedicated MATH layer.** Cleanest for a large set (40+ symbols) and the
only option if you want all of them, but it needs a layer key, and every layer
key on these boards is already assigned — so it would mean displacing something
or adding a combo.

### Considerations before doing it

- **Each include is cheap but the aliases are not free**: an `&uc` binding is a
  2-cell behavior, so a 40-symbol layer is a substantial devicetree addition.
  Only include the specific `blocks/*.h` files needed — `keys-extra.h` pulls in
  all 319 blocks.
- **OS-side requirement is unchanged**: these are unicode input, so they depend
  on the mode currently selected (`UC_MODE_WIN_COMPOSE` by default, with the
  `UXL`/`UXW`/`UXM` leader sequences and the BLUETH profile keys switching it).
  Typing ∑ on a Linux machine without the mode switched will produce garbage.
- **Three blocks were needed for the fractions and super/subscripts** because
  Unicode does not group them; expect the same for math. Concretely, `±` is
  **not** in `mathematical_operators.h` — it is `UC_PLUS_MINUS_SIGN` (U+00B1) in
  `latin_1_supplement.h`, the same block that holds ¹²³ and ¼ ½ ¾. Likewise
  `⟂` is in `miscellaneous_mathematical_symbols_a.h`, not the operators block.
  Check every name against the header rather than assuming the grouping.

---

## 7. Smaller items, lower value

**a. `corne_left.conf` / `corne_right.conf`** contain only
`CONFIG_ZMK_SPLIT_ROLE_CENTRAL=y` / `=n`. Corne is built from upstream's CRKBD
shield, which already handles the central/peripheral split, so these may be
redundant. Worth confirming, not worth guessing.

Verified since: the conf/shield mapping is otherwise consistent. Every shield in
`build.yaml` has a matching `.conf` except `settings_reset`, which deliberately
has none (it only resets stored settings).

**b. `pre-commit` has exactly one active hook** (`zizmor`); everything else is
commented out. A YAML linter would have caught the malformed `build.yaml`
indentation that slipped in during the refactor, and a shell linter would cover
the Justfile recipes.

**c. `generate_leader_yaml.py` is bespoke** (310 lines) purely because
keymap-drawer cannot discover leader sequences. It is now doing pagination,
which is more logic than when it was written. Worth re-reading before the next
change to it — but there is no obvious way to delete it while
`zmk-leader-key` is in use.

**d. `m_ao` uses `&kp LC(LS(L))`** where the other three Outlook macros use the
same. **This is not a bug** — it was verified as consistent across all four and
present in the original config, so it appears to be an intentional Word shortcut.
Recorded here only so it does not get "fixed" by mistake later.

**e. `zmk_macro_gen.py` is a working but undocumented tool** (208 lines). It
turns typed text into a `ZMK_MACRO` block, which is presumably how the 43
signature macros were written. It still runs correctly. It is not referenced
from the README or the Justfile, so it is discoverable only by noticing the file.

---

## 8. Dead and duplicated configuration — **partly fixed**

The result of a systematic sweep for duplication, staleness and
inconsistencies across every non-vendored file. Each finding was confirmed by
reading the source of the thing that consumes it, not by inspection alone.

### a. ~~Three dead `zmk_combos` entries~~ — FIXED

`keymap_drawer.config.yaml` has a `zmk_combos` block matched against the
**devicetree node name** (`zmk.py`: `self.cfg.zmk_combos.get(node.name, {})`),
which for `ZMK_COMBO(x, ...)` is `combo_x`. Three entries named nodes that do
not exist, so they silently did nothing — keymap-drawer never validates
unmatched keys. All three names are corrected, and the silent-failure behaviour
is now noted inline in the config.

Still open: **3 commented-out** entries reference combos that do not exist
(`combo_at`, `combo_underscore`, `combo_leader`) and could go. The other 11
commented entries are valid alternatives, kept deliberately.

### b. The tempest and seppelit shields are near-duplicates

The two shields are the same hardware definition twice. After the Studio change
added the layouts files, the differences are:

| file | difference |
|---|---|
| `*.dtsi` | 4 lines: the layout include, the `zmk,physical-layout` label |
| `*-layouts.dtsi` | 8 lines: comment, node label, `display-name` |
| `*_left.overlay` | one line: the `#include` filename |
| `*_right.overlay` | same single-line difference |
| `Kconfig.defconfig` | shield symbol name, plus `default "HeiKey"` vs `"Seppelit"` |
| `Kconfig.shield` | symbol names only |
| `*.zmk.yml` | name and identifier only |

So roughly **350 lines are duplicated to express one different name**. These
are genuinely two keyboards, so a shared definition is not automatically right —
but the matrices are identical, and if that is by design rather than coincidence
a common `.dtsi` with two thin wrappers would remove the duplication.

Note `Kconfig.defconfig` also disagrees with the `.conf` files about the
keyboard name: it says `default "Seppelit"` while `config/seppelit.conf` sets
`CONFIG_ZMK_KEYBOARD_NAME="HeiKey"`. The `.conf` wins, so the Kconfig default is
dead — but the two should not disagree.

### c. `&sl`, `&uc` and `&msc` are property overrides, not missing macro uses

Three `&node { ... }` blocks override ZMK core nodes. These are sometimes
suggested as `ZMK_STICKY_KEY` / `ZMK_INPUT_TWO_AXIS` candidates, and they are
**not** — those macros *define a new behavior*, whereas these *change properties
on an existing one*. Converting would replace ZMK's built-in `sl`/`msc` nodes
with custom ones carrying the same labels, for no benefit and some risk.

The current form is correct and matches what the modules document.

### d. No other duplication found

Checked and clean:

- **Combos**: 41 defined, no duplicate names, no duplicate key-position sets
  within a layer.
- **Layers**: 12, in index order, no duplicate display names.
- **Macros**: 48, no duplicate names.
- **`.conf` files**: after the `common.conf` dedup, each board conf holds only
  what differs.
- **Scripts**: `check_macro_nesting.py` (119 lines) and `verify_equivalence.py`
  (483) share no code worth extracting — different parse strategies and
  different purposes.
- **Unicode blocks**: three includes, each needed for a distinct code point
  range (see item 6).

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

1. **Local build (item 1)** — needs disk space first, but this is the one that
   changes how fast every later change is verified, and it is the only way to
   test the Studio work that is currently unbuilt.
2. **Wire the harness and nesting guard into CI (item 4)** — protects everything
   else on this list.
3. **CI hygiene (item 2)** — concurrency and `amend_commit`; removes recurring
   friction.
4. **Config inconsistencies (item 3).**
5. **Documentation (item 5)** — the unicode/Greek setup notes are the most
   valuable gap, since that feature has OS-dependent prerequisites.
6. **Shield duplication (item 8b)** — only after confirming the two boards
   genuinely share a matrix.
7. **Math symbols (item 6)** — optional and additive; pick the mechanism first,
   since the free-space survey shows NUMNAV/MEDIA have room and SYMBOL does not.

---

## Related: what the harness now checks

Since this document was first written, `scripts/verify_equivalence.py` was
extended while adding the fractions and super/subscripts:

- combos are identified by **(positions, layers)** rather than by rendered
  legend. Keying on the legend broke twice in one session merely by adding a
  drawing label; position keys are what ZMK itself matches on.
- additions must be acknowledged in `EXPECTED_ADDED_COMBOS`, which now accepts
  globs and a `"*"` entry covering every board. A **removed** combo always fails.
- the golden reference was migrated to the new keys and its leftover legend-dedup
  suffixes removed.

This matters for any combo work: a change that merely relabels a combo no
longer trips the harness, but one that *moves* a combo still does.

Note the harness cannot catch everything. It compares parsed keymaps, so it does
not see devicetree structural errors — the `ZMK_MOD_MORPH` nesting bug passed
both `keymap parse` and the harness while failing the firmware build. That is
what `just verify-nesting` (added alongside it) covers, and it is the strongest
argument for item 1: a local build subsumes both.
