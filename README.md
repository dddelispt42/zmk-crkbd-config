# Heiko's zmk-config for corne/sweep/tempest

<!--toc:start-->
- [Heiko's zmk-config for corne/sweep/tempest](#heikos-zmk-config-for-cornesweeptempest)
  - [Overview](#overview)
  - ["Tempest" split keyboard](#tempest-split-keyboard)
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
layout (macOS/Linux/Windows).

Both German and Portuguese keyboard layouts are terrible for programming,
but this is taken care of the the layers. There are some layers for specific
application with bad default support for keyboard centric workflows
(e.g. MS Outlook).

## "Tempest" split keyboard

![Sweep/Cradio](./img/tempest.svg)

<details>
  <summary>Sweep/Cradio style keyboard</summary>

![Sweep/Cradio](./img/cradio.svg)
</details>

<details>
  <summary>Corne style (CRKBD) keyboard</summary>

![Sweep/Cradio](./img/corne.svg)
</details>
