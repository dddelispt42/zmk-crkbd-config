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

/*
 * Math symbol blocks, for the NUMNAV fractions, superscripts and subscripts.
 *
 * Three blocks are needed rather than one, because Unicode does not group these
 * together:
 *
 *   latin_1_supplement            ¹ ² ³ (U+00B9/B2/B3) and ¼ ½ ¾
 *   superscripts_and_subscripts   ⁰ ⁴..⁹ ⁺ ⁻ ⁼ and all subscripts
 *   number_forms                  the remaining 16 vulgar fractions (⅐ ⅓ ⅔ ...)
 *
 * <zmk-unicode/keys-extra.h> would cover all of them, but it pulls in all 319
 * Unicode blocks, so the specific ones are included instead.
 */
#include <zmk-unicode/keys/blocks/latin_1_supplement.h>
#include <zmk-unicode/keys/blocks/superscripts_and_subscripts.h>
#include <zmk-unicode/keys/blocks/number_forms.h>

/*
 * COMBINING marks, for LaTeX/typst-style math notation: x-bar, vectors, hats,
 * carons and the like.
 *
 * These are NOT from zmk-unicode. That module ships 319 blocks and none of them
 * is the combining-marks block, so there is no UC_* alias for U+0304 and
 * friends - it has MACRON only as precomposed letters (a-macron, a-breve). The
 * aliases are therefore defined here directly.
 *
 * WHAT "COMBINING" MEANS, AND WHY IT IS NOT THE SAME AS THE ACCENT LAYER
 *
 * A combining mark is typed AFTER its base character and attaches to it:
 *
 *     x  then  U+0304  ->  x-bar     (one visual glyph, two code points)
 *     v  then  U+20D7  ->  v-vector
 *
 * The marks already on the ACCENT layer are a different kind of character -
 * spacing accents (category Sk/Sm) like the standalone diaeresis and acute,
 * which sit on the baseline and do not attach to anything. Both kinds are
 * useful and they coexist: the spacing ones for typing, these for math.
 *
 * Every code point below was checked against Python's unicodedata, and all but
 * U+20DD are category Mn (non-spacing mark). U+20DD is Me (enclosing mark): it
 * wraps the base character rather than sitting above it, e.g. a with a circle
 * around it. It is typed the same way, base first.
 *
 * The &uc behavior takes a raw two-cell code point, which is exactly the form
 * these defines use, so no wrapper is needed.
 */

/* Above: the standard accent set */
#define UC_COMBINING_GRAVE               0x0300  0  /* combining grave */
#define UC_COMBINING_ACUTE               0x0301  0  /* combining acute */
#define UC_COMBINING_CIRCUMFLEX          0x0302  0  /* combining circumflex (hat) */
#define UC_COMBINING_TILDE               0x0303  0  /* combining tilde */
#define UC_COMBINING_MACRON              0x0304  0  /* combining macron (bar, mean) */
#define UC_COMBINING_OVERLINE            0x0305  0  /* combining overline */
#define UC_COMBINING_BREVE               0x0306  0  /* combining breve */
#define UC_COMBINING_DOT_ABOVE           0x0307  0  /* combining dot above */
#define UC_COMBINING_DIAERESIS           0x0308  0  /* combining diaeresis */
#define UC_COMBINING_RING_ABOVE          0x030A  0  /* combining ring above */
#define UC_COMBINING_DOUBLE_ACUTE        0x030B  0  /* combining double acute */
#define UC_COMBINING_CARON               0x030C  0  /* combining caron (hacek) */
#define UC_COMBINING_DOUBLE_GRAVE        0x030F  0  /* combining double grave */
#define UC_COMBINING_INVERTED_BREVE      0x0311  0  /* combining inverted breve */
#define UC_COMBINING_COMMA_ABOVE         0x0313  0  /* combining comma above */

/* Above: arrows and harpoons, as used for vectors */
#define UC_COMBINING_LEFT_ARROW_ABOVE        0x20D6  0  /* combining left arrow */
#define UC_COMBINING_RIGHT_ARROW_ABOVE       0x20D7  0  /* combining right arrow */
#define UC_COMBINING_LEFT_RIGHT_ARROW_ABOVE  0x20E1  0  /* combining left-right arrow */
#define UC_COMBINING_LEFT_HARPOON_ABOVE      0x20D0  0  /* combining left harpoon */
#define UC_COMBINING_RIGHT_HARPOON_ABOVE     0x20D1  0  /* combining right harpoon */

/* Enclosing: wraps the base character */
#define UC_COMBINING_ENCLOSING_CIRCLE    0x20DD  0  /* circle around the char */

/* Below: the two with real math use */
#define UC_COMBINING_DOT_BELOW           0x0323  0  /* combining dot below */
#define UC_COMBINING_MACRON_BELOW        0x0331  0  /* combining macron below */

/*
 * Deliberately NOT defined: ring below, cedilla, ogonek and low line as
 * below-marks, and every enclosing variant other than the circle.
 *
 * The ACCENT layer has 28 free cells on both boards (verified by counting the
 * &trans entries in the parsed keymap: 36 bindings with 8 used on the 36-key
 * boards, 34 with 6 used on sweep - 28 free either way). The 26 marks above
 * leave 2 spare. The four omitted ones are the least used in LaTeX/typst math;
 * add them here if a use appears.
 */

/* Overlays: strike-through and cancellation marks */
#define UC_COMBINING_SHORT_STROKE_OVERLAY  0x0335  0  /* short stroke overlay */
#define UC_COMBINING_LONG_STROKE_OVERLAY   0x0336  0  /* long stroke overlay (cancel) */
#define UC_COMBINING_LONG_SOLIDUS_OVERLAY  0x0338  0  /* long solidus (not-equal slash) */

/*
 * zmk-auto-layer: provides &num_word.
 *
 * &num_word LAYER activates LAYER and keeps it active for as long as only
 * digits and the keys in its continue-list are pressed, dropping it on any
 * other key. The module's num_word instance already has `ignore-numbers` and
 * a continue-list of BSPC DEL DOT COMMA PLUS MINUS STAR FSLH EQUAL, which is
 * what we want unchanged - so no override is needed here.
 *
 * It is bound to a T+Y combo in combos.dtsi.
 */
#include <behaviors/num_word.dtsi>

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

/*
 * Macro timing.
 *
 * wait-ms is the delay before triggering the NEXT behavior in the binding list,
 * tap-ms the delay between press and release of a tapped binding (per ZMK's
 * macro_base.yaml). Both are used by every ZMK_MACRO in macros.dtsi.
 *
 * wait-ms was 0, which queues all bindings back-to-back with no gap. The longer
 * signature macros (m_sig_mo is 21 keys) then drop or fuse events on some
 * hosts - observed as a missing RET in one run and an un-released final O in
 * another, on both Linux and Windows. That points at the burst rather than at
 * any one host or the leader key itself.
 *
 * These are the same defaults zmk-unicode needed for its input sequences, and
 * the same reasoning applies: give the host time to see each key separately.
 * The cost is a few tens of ms per macro invocation.
 */
#define MACRO_TAP 20
#define MACRO_WAIT 8

/* Short aliases used throughout the layer/behaviour definitions. */

/*
 * Bluetooth profiles.
 *
 * Profile 0 is the Windows machine; profiles 1-4 are Linux machines running
 * fcitx5. Selecting a profile ALWAYS also switches the unicode input mode, so
 * the BLUETH layer uses the bt_* macros from macros.dtsi rather than &bt BT_SEL
 * directly - each one sets the profile and the matching mode together.
 *
 * There is deliberately no plain "select profile only" alias: a bare profile
 * switch would leave the unicode mode pointing at the previously connected
 * machine, so every profile key would need a second press to fix the mode.
 * Use the bt_* macros.
 */
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
