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

## 2. Extending the symbol sets beyond the current 500/500 — **optional**

The original plan for this chapter was to add math symbols to NUMNAV. That is
no longer how it works: symbols are reached through **leader1**, using
typst/LaTeX names, which scales far better than a dozen spare keys ever could.

What exists now:

| set | active | present but commented |
|---|---|---|
| math symbols | 977 | 31 |
| emoji | 1,260 | 126 |

plus 19 vulgar fractions and the super/subscripts on NUMNAV, 26 combining marks
on the ACCENT layer, and Greek via `leader1 + G` (Shift for capitals).

### Extending it

Change the counts and re-run the generator; no hand editing:

```sh
./scripts/gen_leader_symbols.py --math 700 --emoji 800
```

Constraints to keep in mind:

* **`CONFIG_ZMK_LEADER_MAX_SEQUENCES`** is per leader instance and currently
  3072 against 2286 in use. The build asserts it, which is how both previous
  jumps were caught.
* **Flash**: each active sequence costs `16 + 4 * MAX_KEYS_PER_SEQUENCE` bytes,
  so the current 2,286 are roughly 321 KB of the 1 MB available.
* **Prefix-freeness**: the generator resolves conflicts by renaming, but the
  name space is a tree, so every rename consumes a name.

### What is NOT done

* 31 math symbols and 126 emoji remain commented. Most clash with a name that
  is already taken; the emoji include 31 labelled CJK/button glyphs (🅱, 🆑, 🈂)
  which are deliberately skipped because they are buttons rather than
  pictographs and their short names shadow hundreds of real emoji.
* No `just` recipe wraps the generator yet — it is invoked directly.

## Things that are fine as they are

Worth stating explicitly, because they look like problems and are not:

- **`config/cradio.conf` is named after the shield, not the board.** ZMK loads
  `config/<shield>.conf`, and sweep's shields are `cradio_left`/`cradio_right`.
  Renaming it to `sweep.conf` silently disables every setting on that board —
  which is exactly the regression that was found and fixed during the refactor.
- **`.conf` files cannot `#include` each other.** Kconfig fragments are merged,
  not textually included. The `common.conf` + `EXTRA_CONF_FILE` arrangement is
  the supported mechanism.
- **`config/corne_left.conf` / `corne_right.conf` are gone, deliberately.**
  They only set `CONFIG_ZMK_SPLIT_ROLE_CENTRAL`, and upstream's corne shield
  already defaults it: `Kconfig.defconfig` has `if SHIELD_CORNE_LEFT` →
  `ZMK_SPLIT_ROLE_CENTRAL default y`, with right taking the implicit `n`. The
  local tempest and seppelit shields set it in their own `Kconfig.defconfig`
  for the same reason. Do not re-add the files.
- **`&leader1` is on a combo for sweep.** A 34-key board has no `LH2`, and no
  main key is free on any of the 12 layers, so a dedicated chord is the only way
  to keep the leader reachable there.

---

## Also worth doing, but small

Two loose ends that do not warrant a chapter of their own:

* **Three stale commented entries in `keymap_drawer.config.yaml`.** The
  `zmk_combos` block is matched against the devicetree node name, so
  `combo_at`, `combo_underscore` and `combo_leader` refer to combos that do not
  exist. The other 11 commented entries are valid alternatives. Note that
  keymap-drawer never warns about an unmatched key, which is how the three dead
  *active* entries hid for so long before they were fixed.
* **The zizmor pre-commit hook points at a moved repository.**
  `woodruffw/zizmor-pre-commit` now redirects to `zizmorcore/zizmor-pre-commit`.
  The pinned version is current and the redirect works, so nothing is broken,
  but it is worth repointing.

---

## Suggested order

1. **Local build (chapter 1)** — needs disk space first, but it is the only way
   to verify the leader-symbol work without a CI round trip.
2. **Wire `just verify` and `just verify-nesting` into CI** — they exist and pass
   locally, but nothing runs them on a push, so a regression reaches the branch
   before it is noticed.
3. **The small items above** — minutes of work each.
4. **Extend the symbol sets (chapter 2)** — only if 500/500 turns out not to be
   enough in practice.
