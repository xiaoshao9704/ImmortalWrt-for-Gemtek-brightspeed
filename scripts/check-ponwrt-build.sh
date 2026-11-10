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
# The AN7581 direct-PLL CPU frequency scaling is not used: naoki66 reproduced
# a CPU1 fault within a minute with it enabled on the same SoC (16aa9e1c9b).
# The board DTS must stay on the ponwrt OPP table (top 1.2 GHz) without the
# direct-PLL opt-in or the extra 1.25-1.4 GHz and SMCC 15-18 levels.
for opp in opp-1250000000 opp-1300000000 opp-1350000000 opp-1400000000; do
	if fdtget -l "$dtb" /opp-table | grep -Fxq "$opp"; then
		fail "overclock OPP $opp is present"
	fi
done
for level in opp15 opp16 opp17 opp18; do
	if fdtget -l "$dtb" /opp-table-cpu-smcc | grep -Fxq "$level"; then
		fail "overclock SMCC level $level is present"
	fi
done
if fdtget -p "$dtb" /cpufreq | grep -Fxq 'airoha,force-direct-pll'; then
	fail "direct PLL opt-in is present"
fi
if fdtget -t s "$dtb" /chosen bootargs | grep -Fq 'cpufreq.default_governor='; then
	fail "board DTS overrides the cpufreq governor"
fi
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
