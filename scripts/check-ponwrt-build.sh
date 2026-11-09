#!/usr/bin/env bash
# Inspect the completed OpenWrt build, not a seed config or a patch file.
set -Eeuo pipefail

if (( $# != 3 )); then
	echo "usage: $0 <expanded-config> <linux-build-directory> <target-artifact-directory>" >&2
	exit 2
fi
config="$1"
kernel="$2"
target="$3"
root="$(cd "$(dirname "$0")/.." && pwd)"
report="$target/ponwrt-verification"
mkdir -p "$report"
fail() { echo "ponwrt verification: $*" >&2; exit 1; }

[[ -s "$config" && -s "$kernel/.config" ]] || fail "missing generated configuration"
cp "$config" "$report/openwrt.config"
cp "$kernel/.config" "$report/kernel.config"

flow="$kernel/net/netfilter/nf_flow_table_inet.ko"
[[ -s "$flow" ]] || fail "missing compiled nf_flow_table_inet.ko"
readelf -p .modinfo "$flow" > "$report/flowtable-modinfo.txt"
grep -Fq 'alias=nf-flowtable-7' "$report/flowtable-modinfo.txt" || fail "bridge flowtable alias is absent"

# Keep both the prepared sources and emitted ARM64 code as review evidence.
# The source checks catch a dropped 920-17; the objects must also exist.
ether="$kernel/drivers/net/ethernet/airoha"
for name in eth ppe; do
	[[ -s "$ether/airoha_$name.o" ]] || fail "missing compiled airoha_$name.o"
	grep -Fq 'PPPOE_SES_HLEN' "$ether/airoha_$name.c" || fail "PPPoE frame overhead missing in $name"
	cp "$ether/airoha_$name.c" "$report/"
done
grep -Fq 'test_bit(AIROHA_DEV_F_PON' "$ether/airoha_ppe.c" || fail "old PON flag API"
nm "$ether/airoha_ppe.o" | grep -E '[[:space:]]T[[:space:]]airoha_ppe_set_xmit_frame_size$' >/dev/null \
	|| fail "PPE frame-size function was not compiled"
objdump="${OBJDUMP:-}"
if [[ -z "$objdump" ]]; then
	for candidate in "$root"/staging_dir/toolchain-*/bin/*-objdump; do
		[[ -x "$candidate" ]] || continue
		objdump="$candidate"
		break
	done
fi
[[ -n "$objdump" ]] || fail "cross objdump is unavailable"
"$objdump" -dr --disassemble=airoha_ppe_set_xmit_frame_size "$ether/airoha_ppe.o" \
	> "$report/ppe-frame-size.asm"
"$objdump" -dr --disassemble=airoha_dev_set_xmit_frame_size "$ether/airoha_eth.o" \
	> "$report/mac-frame-size.asm"

if grep -Eq '^CONFIG_(TARGET_airoha_an7581_DEVICE|TARGET_DEVICE_airoha_an7581_DEVICE)_gemtek_xg2010g-2g-ubi=y$' "$config"; then
	dts=an7581-gemtek-xg2010g-2g-ubi
else
	dts=an7581-gemtek-xg2010g-ubi
fi
dtb="$kernel/../image-$dts.dtb"
[[ -s "$dtb" ]] || fail "missing compiled $dts.dtb"
[[ "$(fdtget -t u "$dtb" /opp-table/opp-1400000000 opp-hz)" == '0 1400000000' ]] \
	|| fail "1.4 GHz OPP is absent"
[[ "$(fdtget -t u "$dtb" /opp-table-cpu-smcc/opp18 opp-level)" == 18 ]] \
	|| fail "SMCC OPP18 is absent"
[[ "$(fdtget -t x "$dtb" /opp-table/opp-1400000000 required-opps)" == \
	"$(fdtget -t x "$dtb" /opp-table-cpu-smcc/opp18 phandle)" ]] \
	|| fail "CPU and SMCC OPPs are not linked"
fdtget -p "$dtb" /cpufreq | grep -Fxq 'airoha,force-direct-pll' || fail "direct PLL opt-in is absent"
fdtget -t s "$dtb" /chosen bootargs | grep -Fq 'cpufreq.default_governor=powersave' \
	|| fail "early boot governor changed"
cp "$dtb" "$report/"

mapfile -t manifests < <(find "$target" -maxdepth 1 -type f -name '*manifest' | sort)
(( ${#manifests[@]} > 0 )) || fail "no image manifest"
for manifest in "${manifests[@]}"; do
	grep -Eq '^kmod-airoha-xpon[[:space:]]+-[[:space:]]+[^[:space:]]*-r71$' "$manifest" \
		|| fail "airoha-xpon r71 missing from $manifest"
	bash "$root/scripts/check-gemtek-profile-isolation.sh" \
		--config "$config" --kernel-config "$kernel/.config" --manifest "$manifest"
	python3 "$root/scripts/check-installed-package-baseline.py" \
		--config "$config" --manifest "$manifest" \
		--report "$report/$(basename "$manifest").baseline.json"
	awk '{ print $1 }' "$manifest" | sort -u > "$report/$(basename "$manifest").packages"
done
echo "ponwrt verification passed; evidence: $report"
