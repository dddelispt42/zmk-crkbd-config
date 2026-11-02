#!/usr/bin/env python3
"""
Check that no macro queues more events than the behaviour queue can hold.

Why this exists
---------------
ZMK's behaviour queue is a fixed-size pool and `zmk_behavior_queue_add` calls
`k_msgq_put(..., K_NO_WAIT)`: when the queue is full the event is DISCARDED and
the error is dropped on the floor. There is no build error and no runtime
warning - the macro simply stops partway.

The failure mode is confusing rather than obvious. `m_sig_tb` was 33 keys = 66
events against the default pool of 64, so the final release was dropped and `O`
stayed held down on the host, auto-repeating. It looked like a stuck key, not a
truncated macro.

Each `&kp` costs two events (press then release), so the usable macro length is
half the queue size.

Usage
-----
    ./scripts/check_macro_queue.py

Exits non-zero if any macro would overflow, so it works as a pre-commit or CI
gate.
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
MACROS = REPO / "config" / "include" / "macros.dtsi"
CONFS = [REPO / "config" / "common.conf", *sorted((REPO / "config").glob("*.conf"))]

# ZMK's default when CONFIG_ZMK_BEHAVIORS_QUEUE_SIZE is not set.
DEFAULT_QUEUE = 64

# Bindings that consume queue slots. `&kp` costs 2 (press + release); the
# control bindings and the non-tap behaviours cost 1.
TWO_EVENT = re.compile(r"&kp\s")
ONE_EVENT = re.compile(r"&(?:bt|uc|msc|sl|mo|to|tog|mt|lt)\s")


def queue_size() -> tuple[int, str]:
    """The configured queue size and where it came from."""
    for conf in CONFS:
        if not conf.is_file():
            continue
        for m in re.finditer(
            r"^\s*CONFIG_ZMK_BEHAVIORS_QUEUE_SIZE\s*=\s*(\d+)", conf.read_text(), re.M
        ):
            if "n" not in m.group(1):
                return int(m.group(1)), conf.name
    return DEFAULT_QUEUE, "ZMK default"


def macros() -> list[tuple[str, int]]:
    """(name, event count) for each macro, in file order."""
    text = MACROS.read_text(encoding="utf-8")
    text = re.sub(r"//[^\n]*", "", text)  # comments can hold `&kp` in prose
    out = []
    for m in re.finditer(r"ZMK_MACRO\(\s*(\w+),(.*?)\n\s*\)", text, re.S):
        name, body = m.group(1), m.group(2)
        events = len(TWO_EVENT.findall(body)) * 2 + len(ONE_EVENT.findall(body))
        out.append((name, events))
    return out


def main() -> int:
    if not MACROS.is_file():
        print(f"FAIL - {MACROS} not found")
        return 1

    size, origin = queue_size()
    print(f"queue size {size} (from {origin})")

    over = [(n, e) for n, e in macros() if e > size]
    longest = max(macros(), key=lambda x: x[1])
    print(f"  longest macro: {longest[0]} at {longest[1]} events "
          f"(limit {size}, headroom {size - longest[1]})")

    if over:
        print()
        for name, events in over:
            print(f"FAIL - {name} needs {events} events, over by {events - size}")
        print()
        print("  ZMK drops the excess silently, so the macro is truncated and a")
        print("  key can be left held down. Raise CONFIG_ZMK_BEHAVIORS_QUEUE_SIZE.")
        return 1

    print("OK - every macro fits in the queue")
    return 0


if __name__ == "__main__":
    sys.exit(main())
