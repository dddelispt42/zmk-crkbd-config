#!/bin/bash
chmod +w ./*.keymap
# grep -v "NOT-FOR-CORNE" keymap | sed 's/DK/\&none/g' | sed 's/RKL/\&leader1/g;s/RKR/\&key_repeat/g' >./corne.keymap
grep -v "NOT-FOR-CORNE" keymap | sed 's/DK/\&none/g' | sed 's/RKL/\&none/g;s/RKR/\&key_repeat/g' >./corne.keymap
grep -v "NOT-FOR-SWEEP" keymap | sed 's/DK//g' | sed 's/RKL//g;s/RKR//g' >./cradio.keymap
chmod -w ./*.keymap
if command -v keymap >/dev/null; then
	keymap -c ./keymap-drawer.yaml parse -c 10 -z cradio.keymap >sweep_keymap.yaml
	keymap -c ./keymap-drawer.yaml parse -c 10 -z corne.keymap >corne_keymap.yaml
	keymap -c ./keymap-drawer.yaml draw sweep_keymap.yaml >../sweep_keymap.ortho.svg
	keymap -c ./keymap-drawer.yaml draw corne_keymap.yaml >../corne_keymap.ortho.svg
	trash sweep_keymap.yaml corne_keymap.yaml
fi
