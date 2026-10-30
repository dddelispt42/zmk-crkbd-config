/*
 * Shared keymap preamble.
 *
 * Included by every keyboard keymap BEFORE the behaviour/macro/combo/layer
 * includes. It pulls in ZMK's bindings, zmk-helpers, and this board's
 * key-labels header, and defines the tuning constants the rest of the config
 * refers to.
 *
 * Board selection
 * ---------------
 * The including keymap must define exactly one of:
 *
 *     #define ZMK_KB_36     36-key boards: corne (5 columns), tempest, seppelit
 *     #define ZMK_KB_34     34-key boards: sweep / cradio
 *
 * That chooses the zmk-helpers key-labels header, which is what makes one set
 * of combos/layers work across keyboards with different key-position
 * numbering. Note the two headers do NOT agree on numbering for the outer
 * thumb keys (36.h: LH0=32, 34.h: LH0=31), which is precisely why positions
 * are written as labels rather than numbers.
 */

#pragma once

#include <behaviors.dtsi>
#include <dt-bindings/zmk/keys.h>
#include <dt-bindings/zmk/bt.h>
#include <dt-bindings/zmk/outputs.h>
#include <dt-bindings/zmk/mouse.h>

#undef ZMK_POINTING_DEFAULT_MOVE_VAL
#define ZMK_POINTING_DEFAULT_MOVE_VAL 1500  // default: 600
#undef ZMK_POINTING_DEFAULT_SCRL_VAL
#define ZMK_POINTING_DEFAULT_SCRL_VAL 30    // default: 10
#include <dt-bindings/zmk/pointing.h>

#ifndef KEYMAP_DRAWER
#include <locale/keys_pt.h>
#endif

/* zmk-helpers: ZMK_LAYER / ZMK_COMBO / ZMK_MACRO / ZMK_HOLD_TAP ... */
#include <zmk-helpers/helper.h>

/*
 * zmk-unicode: provides &uc and the UC_* code point aliases.
 *
 * Importing this header alone is not enough - the module also needs an input
 * system selected, because each OS enters a code point differently. That is set
 * via the `default-mode` property of the &uc behavior (see behaviors.dtsi,
 * which also defines leader sequences to switch it at runtime).
 */
#include <behaviors/unicode.dtsi>
#include <zmk-unicode/keys/greek.h>

/* Per-board position labels. Exactly one must be selected. */
#if defined(ZMK_KB_34)
#include <zmk-helpers/key-labels/34.h>
#elif defined(ZMK_KB_36)
#include <zmk-helpers/key-labels/36.h>
#else
#error "Define ZMK_KB_36 (corne/tempest/seppelit) or ZMK_KB_34 (sweep) before including keys.h"
#endif

/*
 * KEYS_L / KEYS_R / THUMBS come from the key-labels header and are therefore
 * already correct per board - do not redefine them here. They are used for
 * "timeless homerow mods":
 * https://github.com/urob/zmk-config/tree/main#timeless-homerow-mods
 */

/* Combo timing. */
#define COMBO_TIMEOUT 50
#define SPLIT_COMBO_TIMEOUT 75
// 3-finger chords land noticeably further apart than 2-finger ones; the extra
// slack stops S+D+F / X+C+V from missing the combo window. The idle guard -
// not the timeout - is what protects against false positives while typing.
#define LONG_COMBO_TIMEOUT 175

/*
 * Layer indices.
 *
 * These MUST match the order of the ZMK_LAYER definitions in layers.dtsi,
 * because the URML/URMR upper-row-mod macros pass them as behaviour arguments
 * and combos.dtsi references combinations of them.
 *
 * They deliberately share no token with a ZMK_LAYER name: ZMK_LAYER stringifies
 * and token-pastes its argument through the preprocessor, so a layer node named
 * `QWERTY` while `#define QWERTY 0` is in scope would expand to `layer_0` with
 * display-name "0". (The layer nodes are therefore named exactly as before -
 * QWERTY, NUMNAV, ... - and these defines carry the numeric ids.)
 */
#define QWERTY 0
#define NUMNAV 1
#define SYMBOL 2
#define FUNADJ 3
#define MOUSE  4
#define MEDIA  5
#define WMCFG  6
#define MSOUTL 7
#define MACROS 8
#define BLUETH 9
#define LOCK   10
#define ACCENT 11

/* Macro timing. */
#define MACRO_TAP 10
#define MACRO_WAIT 0

/* Short aliases used throughout the layer/behaviour definitions. */
#define BTSEL(profile) &bt BT_SEL profile
#define BTCLR &bt BT_CLR
#define OUTUSB &out OUT_USB
#define OUTBLE &out OUT_BLE

/*
 * ZMK_LAYER_NAMED(node_name, "Display Name", layout)
 *
 * A thin wrapper over zmk-helpers' ZMK_LAYER. It exists for one reason:
 * ZMK_LAYER uses its argument BOTH as the devicetree node name and (stringified)
 * as `display-name`. Since the layer-index defines above are in scope, passing
 * `QWERTY` would expand to `0` and yield `layer_0` with display-name "0" -
 * losing the layer names that the drawings and keymap_drawer.config.yaml use.
 *
 * Separating the two keeps the lowercase node name collision-free while the
 * display name stays exactly what it has always been ("QWERTY", "NUMNAV", ...).
 */
#define ZMK_LAYER_NAMED(_node, _disp, layout) \
    / { \
        keymap { \
            compatible = "zmk,keymap"; \
            layer_ ## _node { \
                display-name = _disp; \
                bindings = <layout>; \
            }; \
        }; \
    };
