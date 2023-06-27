#!/bin/bash
chmod +w ./*.keymap
grep -v "NOT-FOR-CORNE" keymap | sed 's/DK/\&none/g' | sed 's/RK/\&key_repeat/g' >./corne.keymap
grep -v "NOT-FOR-SWEEP" keymap | sed 's/DK//g' | sed 's/RK//g' >./cradio.keymap
chmod -w ./*.keymap
