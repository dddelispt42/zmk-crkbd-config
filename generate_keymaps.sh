#!/bin/bash
chmod +w ./config/*.keymap
# grep -v "NOT-FOR-CORNE" ./config/keymap | sed 's/DK/\&none/g' | sed 's/RKL/\&leader1/g;s/RKR/\&key_repeat/g' >./config/corne.keymap
grep -vE "ONLY-FOR-SWEEP|ONLY-FOR-TEMPEST" ./config/keymap | sed 's/DK/\&none/g' | sed 's/RKL/\&leader1/g;s/RKR/\&key_repeat/g' | sed 's/\s*$//' >./config/corne.keymap
# grep -vE "ONLY-FOR-CORNE|ONLY-FOR-TEMPEST" ./config/keymap | sed 's/DK//g' | sed 's/RKL//g;s/RKR//g' | sed 's/\s*$//' >./config/cradio.keymap
grep -vE "ONLY-FOR-CORNE|ONLY-FOR-SWEEP" ./config/keymap | sed 's/DK//g' | sed 's/RKL/\&leader1/g;s/RKR/\&key_repeat/g' | sed 's/\s*$//' >./config/tempest.keymap
chmod -w ./config/*.keymap

# Leader-key sequences are behavior properties, not key bindings, so
# keymap-drawer cannot discover them. Derive a "virtual layer" YAML from
# config/keymap and hand it to `keymap draw` as an extra merged file.
if [ -x ./generate_leader_yaml.py ]; then
	./generate_leader_yaml.py --source ./config/keymap --out ./config/leader.yaml
fi

if command -v keymap >/dev/null; then
	keymap -c keymap_drawer.config.yaml parse -c 10 -z ./config/corne.keymap >corne_keymap.yaml
	keymap -c keymap_drawer.config.yaml parse -c 10 -z ./config/tempest.keymap >tempest_keymap.yaml
	keymap -c keymap_drawer.config.yaml parse -c 10 -z ./config/seppelit.keymap >seppelit_keymap.yaml
	mkdir -p ~/dl
	keymap -c keymap_drawer.config.yaml draw corne_keymap.yaml ./config/leader.yaml >~/dl/corne_keymap.svg
	keymap -c keymap_drawer.config.yaml draw -j ./config/tempest.json tempest_keymap.yaml ./config/leader.yaml >~/dl/tempest_keymap.svg
	keymap -c keymap_drawer.config.yaml draw -j ./config/seppelit.json seppelit_keymap.yaml ./config/leader.yaml >~/dl/seppelit_keymap.svg
	trash corne_keymap.yaml tempest_keymap.yaml seppelit_keymap.yaml
fi
