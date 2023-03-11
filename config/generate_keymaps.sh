#!/bin/bash
chmod +w ./*.keymap
grep -v "NOT-FOR-CORNE" keymap | sed 's/DK/\&none/g' >./corne.keymap
grep -v "NOT-FOR-SWEEP" keymap | sed 's/DK//g' >./cradio.keymap
chmod -w ./*.keymap
