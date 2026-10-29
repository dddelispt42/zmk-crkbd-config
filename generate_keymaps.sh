#!/bin/bash
set -uo pipefail

chmod +w ./config/*.keymap
# grep -v "NOT-FOR-CORNE" ./config/keymap | sed 's/DK/\&none/g' | sed 's/RKL/\&leader1/g;s/RKR/\&key_repeat/g' >./config/corne.keymap
grep -vE "ONLY-FOR-SWEEP|ONLY-FOR-TEMPEST" ./config/keymap | sed 's/DK/\&none/g' | sed 's/RKL/\&leader1/g;s/RKR/\&key_repeat/g' | sed 's/\s*$//' >./config/corne.keymap
# grep -vE "ONLY-FOR-CORNE|ONLY-FOR-TEMPEST" ./config/keymap | sed 's/DK//g' | sed 's/RKL//g;s/RKR//g' | sed 's/\s*$//' >./config/cradio.keymap
grep -vE "ONLY-FOR-CORNE|ONLY-FOR-SWEEP" ./config/keymap | sed 's/DK//g' | sed 's/RKL/\&leader1/g;s/RKR/\&key_repeat/g' | sed 's/\s*$//' >./config/tempest.keymap
chmod -w ./config/*.keymap

# Leader-key sequences are behavior properties, not key bindings, so
# keymap-drawer cannot discover them. Derive a "virtual layer" YAML from
# config/keymap for each keyboard and hand it to `keymap draw` as an extra
# merged file.
#
# The key positions per row differ per keyboard (corne has 5 rows, tempest and
# seppelit have 4), and keymap-drawer validates that the leader layers match the
# physical layout. So the row shape is derived from each parsed keymap rather
# than hardcoded - see _leader_yaml_for below.
generate_leader() {  # $1 = keyboard, $2 = parsed keymap yaml, $3 = out file
	local kb=$1 parsed=$2 out=$3
	[ -x ./generate_leader_yaml.py ] || return 0
	local rows
	rows=$(python3 - "$parsed" <<-'PY'
		import sys, yaml
		layers = yaml.safe_load(open(sys.argv[1]))["layers"]
		first = next(iter(layers.values()))
		print(" ".join(str(len(r)) for r in first))
	PY
	)
	if [ -z "$rows" ]; then
		echo "WARNING: could not determine row shape for $kb, skipping leader layers" >&2
		return 0
	fi
	./generate_leader_yaml.py --source ./config/keymap --rows $rows --out "$out"
}

if command -v keymap >/dev/null; then
	mkdir -p ~/dl
	for kb in corne tempest seppelit; do
		parsed="${kb}_keymap.yaml"
		keymap -c keymap_drawer.config.yaml parse -c 10 -z "./config/${kb}.keymap" >"$parsed" || {
			echo "WARNING: parse failed for $kb, skipping" >&2
			continue
		}
		leader="./config/${kb}-leader.yaml"
		generate_leader "$kb" "$parsed" "$leader"
		if [ -f "./config/${kb}.json" ]; then
			keymap -c keymap_drawer.config.yaml draw -j "./config/${kb}.json" "$parsed" "$leader" >"$HOME/dl/${kb}_keymap.svg"
		else
			keymap -c keymap_drawer.config.yaml draw "$parsed" "$leader" >"$HOME/dl/${kb}_keymap.svg"
		fi
		rm -f "$parsed"
	done
fi
