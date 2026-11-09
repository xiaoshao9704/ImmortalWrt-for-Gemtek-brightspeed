#!/bin/sh
# 第 1 步：推送合併版 PON 驅動和 xg2010g/phase1 分支，驗證後才啟動 CI，最後印出連結。
# 需要：git、gh（brew install gh），並已執行 gh auth login。
# 必要步驟失敗會中止並回傳非 0；main 無法快轉時仍保留已驗證的分支。
# BUNDLE_DIR=/path/to/extracted/phase1 sh scripts/PUSH-phase1.sh
# Bundle 檔案沿用第二版附件，不存入本倉庫。
set -eu
D="${BUNDLE_DIR:-$(cd "$(dirname "$0")" && pwd)}"
D=$(cd "$D" && pwd) || { echo "錯誤：無法進入 bundle 目錄" >&2; exit 1; }
W="${WORKDIR:-$HOME/pr-work}"
ME="${GH_USER:-xiaoshao9704}"
GH_HOST_URL="${GH_HOST_URL:-https://github.com}"
PON_COMMIT=fec6b02eae6ccca8e8313d171102670183224b02
PHASE1_COMMIT=412f5053ebf0f750d440393f9c1f621d353a2348
PON_URL="$GH_HOST_URL/$ME/openwrt-pon-drivers.git"
FORK_URL="$GH_HOST_URL/$ME/ImmortalWrt-for-Gemtek-brightspeed.git"

die() { echo "錯誤：$*" >&2; exit 1; }

for bundle in pon-drivers.bundle fork-phase1.bundle; do
	[ -f "$D/$bundle" ] || die "缺少 $D/$bundle；請設定 BUNDLE_DIR 為第二版附件的解壓目錄"
done

# 遠端分支的 tip 必須正好是預期的 commit
remote_tip_is() { # url ref sha
	out=$(git ls-remote "$1" "refs/heads/$2") || die "無法讀取 $1（git ls-remote 失敗）"
	tip=$(printf '%s\n' "$out" | awk 'NR==1{print $1}')
	[ -n "$tip" ] || die "$1 上找不到分支 $2"
	[ "$tip" = "$3" ] || die "$1 的 $2 是 $tip，預期 $3"
}

mkdir -p "$W" || die "無法建立工作目錄 $W"
cd "$W" || die "無法進入工作目錄 $W"

echo "== 1/4 fork pbs05/openwrt-pon-drivers 並推送合併版"
gh repo view "$ME/openwrt-pon-drivers" >/dev/null 2>&1 || gh repo fork pbs05/openwrt-pon-drivers --clone=false || die "fork 失敗"
[ -d openwrt-pon-drivers ] || git clone "$PON_URL" || die "clone $PON_URL 失敗"
(
	cd openwrt-pon-drivers || die "無法進入 PON 驅動目錄"
	git fetch -q "$GH_HOST_URL/pbs05/openwrt-pon-drivers.git" main || die "抓取 PON 上游 main 失敗"
	git fetch -q "$D/pon-drivers.bundle" +xg2010g-merged:xg2010g-merged || die "匯入 PON bundle 失敗"
	[ "$(git rev-parse xg2010g-merged)" = "$PON_COMMIT" ] || die "bundle 內容不是預期的 $PON_COMMIT"
	git push -u origin xg2010g-merged || die "推送 xg2010g-merged 失敗"
	# 讓 main 快轉到合併版；main 若已有別的提交會被拒絕，這時保留分支即可
	git push origin xg2010g-merged:main || echo "注意：main 無法快轉，feed 仍可從 xg2010g-merged 分支取得該 commit"
)
remote_tip_is "$PON_URL" xg2010g-merged "$PON_COMMIT"

echo "== 2/4 推送 xg2010g/phase1"
[ -d ImmortalWrt-for-Gemtek-brightspeed ] || git clone --filter=blob:none "$FORK_URL" || die "clone $FORK_URL 失敗"
(
	cd ImmortalWrt-for-Gemtek-brightspeed || die "無法進入韌體目錄"
	git fetch -q origin main || die "抓取韌體 main 失敗"
	git fetch -q "$D/fork-phase1.bundle" +xg2010g/phase1:xg2010g/phase1 || die "匯入韌體 bundle 失敗"
	[ "$(git rev-parse xg2010g/phase1)" = "$PHASE1_COMMIT" ] || die "bundle 內容不是預期的 $PHASE1_COMMIT"
	feed_config=$(git show xg2010g/phase1:feeds.conf.default) || die "無法讀取 feeds.conf.default"
	printf '%s\n' "$feed_config" | grep -qF "openwrt-pon-drivers.git^$PON_COMMIT" || die "feeds.conf.default 沒有指向 $PON_COMMIT"
	git push -u origin xg2010g/phase1 || die "推送 xg2010g/phase1 失敗"
)
remote_tip_is "$FORK_URL" xg2010g/phase1 "$PHASE1_COMMIT"

echo "== 3/4 用 CI 相同的方式抓取 feed commit（git fetch --depth=1 origin <sha>）"
T=$(mktemp -d) || die "無法建立暫存目錄"
trap 'rm -rf "$T"' EXIT
git -C "$T" init -q || die "git init 失敗"
git -C "$T" fetch -q --depth=1 "$PON_URL" "$PON_COMMIT" || die "無法從 $PON_URL 抓取 $PON_COMMIT，CI 的 feeds update 會失敗"
git -C "$T" cat-file -e "$PON_COMMIT^{commit}" || die "抓到的內容不包含 $PON_COMMIT"
echo "OK：$PON_COMMIT 可以被 feeds update 取得"

CI_STATUS=0
if [ "${RUN_CI:-1}" = 1 ]; then
	echo "== 4/4 啟動 XG2010G 編譯（不發布 release）"
	gh workflow run build-firmware.yml -R "$ME/ImmortalWrt-for-Gemtek-brightspeed" --ref xg2010g/phase1 \
		-f config_seed=2010.config -f release_type=none || CI_STATUS=1
else
	echo "== 4/4 略過 CI（RUN_CI=0）"
fi

cat <<LINKS

連結：
  PON 驅動分支   https://github.com/$ME/openwrt-pon-drivers/tree/xg2010g-merged
  PON 驅動 commit https://github.com/$ME/openwrt-pon-drivers/commit/$PON_COMMIT
  phase1 分支    https://github.com/$ME/ImmortalWrt-for-Gemtek-brightspeed/tree/xg2010g/phase1
  與 main 比較   https://github.com/$ME/ImmortalWrt-for-Gemtek-brightspeed/compare/main...xg2010g/phase1
  CI 編譯        https://github.com/$ME/ImmortalWrt-for-Gemtek-brightspeed/actions/workflows/build-firmware.yml
LINKS

if [ "$CI_STATUS" != 0 ]; then
	echo "推送與驗證都已完成，但 CI 沒有啟動成功，請到上面的 CI 頁面手動執行。" >&2
	exit 2
fi
echo "完成。"
