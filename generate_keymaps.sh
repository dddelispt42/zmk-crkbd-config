#!/bin/bash
chmod +w ./config/*.keymap
# grep -v "NOT-FOR-CORNE" ./config/keymap | sed 's/DK/\&none/g' | sed 's/RKL/\&leader1/g;s/RKR/\&key_repeat/g' >./config/corne.keymap
grep -vE "NOT-FOR-CORNE|NOT-FOR-TEMPEST" ./config/keymap | sed 's/DK/\&none/g' | sed 's/RKL/\&none/g;s/RKR/\&key_repeat/g' | sed 's/\s*$//' >./config/corne.keymap
# grep -vE "NOT-FOR-SWEEP|NOT-FOR-TEMPEST" ./config/keymap | sed 's/DK//g' | sed 's/RKL//g;s/RKR//g' | sed 's/\s*$//' >./config/cradio.keymap
grep -vE "NOT-FOR-CORNE|NOT-FOR-SWEEP" ./config/keymap | sed 's/DK//g' | sed 's/RKL/&none/g;s/RKR/\&key_repeat/g' | sed 's/\s*$//' >./config/tempest.keymap
chmod -w ./config/*.keymap
if command -v keymap >/dev/null; then
	keymap -c keymap_drawer.config.yaml parse -c 10 -z ./config/corne.keymap >corne_keymap.yaml
	keymap -c keymap_drawer.config.yaml parse -c 10 -z ./config/cradio.keymap >sweep_keymap.yaml
	keymap -c keymap_drawer.config.yaml parse -c 10 -z ./config/tempest.keymap >tempest_keymap.yaml
	keymap -c keymap_drawer.config.yaml draw corne_keymap.yaml >~/dl/corne_keymap.ortho.svg
	keymap -c keymap_drawer.config.yaml draw tempest_keymap.yaml >~/dl/tempest_keymap.ortho.svg
	trash sweep_keymap.yaml corne_keymap.yaml tempest.yeml
fi
