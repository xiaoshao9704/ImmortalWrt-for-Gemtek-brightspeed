# XG2010G 精简固件候选版

本分支从用户 `main`（`d922038f34ec69e734ed27dd1578948c7675a294`）合并
naoki66 公开 `master`（`a6dce40a91ca3f0ebeca9e8f51c8318f4d453eb3`），
不是此前的 ponwrt 迁移分支。详细来源与验证范围见
[合并记录](docs/xg2010g-merge-20261111.md)。

目标为 **XG2010G 1 GiB、OpenWrt U-Boot UBI 布局**。
2010.config 保留 main 的本机 PPPoE、ONU、IPTV、语音、UPnP、NPU、WireGuard、
cryptodev 和中文 LuCI。PBR、在线固件升级和集中管理代理不打包。
2 GiB profile 仍独立保留，但本轮没有构建或精简验收 2 GiB 固件。

## 核心与兼容性

- 当前上游 Linux 6.18.60、Airoha QDMA/PCS/PHY 修复及用户空间基底。
- 按作者安全规避禁用 AN7581 CPU DVFS/直接 PLL，沿用引导程序设定的时钟。
- main 独立 1G/2G DTS、兼容别名、compat 2.0、UBI 布局和升级检查。
- PPP **稳定版 2.5.4**，保留 syncppp、多链路、TDB 和脚本 hook 修复。
- firewall4 错误传播、ONU bridge nft 回退、UPnP counter 和原有 feed 修复。
- 实际使用的公共 feeds 固定 SHA，另应用可审计的 ONU daemon r4 补丁。

## 无在线升级

不导入 firmware_ota feed，不打包 luci-app-naoki66-ota，不加入其菜单、RPC、
下载助手或 Argon 登录自动检查。ac-agent、attendedsysupgrade、auc、owut 也不选。
保留标准手动 sysupgrade 和 LuCI「备份/升级」页面及共用依赖。
CI 分别检查生成配置、实际 manifest 和 rootfs。

## 来源限制

作者 20261111 Release 的镜像 revision 是 8e02d129，公开 tag 却是 a6dce40a。
发行镜像 xPON r69、ONU UI r40 和 OTA 的完整源码没有在相应公共 feed 公开。
本分支使用公共 PON r68，并将公开历史里的 ONU 恢复/MSK 补丁应用到固定源，
得到 daemon r4。缺少基础状态机的 PON RX-stall 增量补丁未强行套用。
不能宣称复现作者整个最新发行版，也不能声称已经修复 PON 注册或启动故障。

## 构建

专用 [候选构建工作流](.github/workflows/build-lean-xg2010g.yml) 只构建 1G
并上传 Actions artifacts，不发布 Release、不打 tag、不刷机。

```sh
./scripts/feeds update -a
./scripts/feeds install -a
FEED_PATCHES_STRICT=1 bash scripts/apply-feed-patches.sh
cp 2010.config .config
make defconfig
UPSTREAM_COMMIT=a6dce40a bash scripts/set-build-version.sh .config
make defconfig
bash scripts/check-distfeeds.sh
bash scripts/check-gemtek-profile-isolation.sh --config .config
python3 scripts/check-lean-firmware.py --config .config
make download -j8
make -j2 world BUILD_LOG=1
```

完整编译结果以对应提交 Actions run 为准。编译和静态检查通过，不等于硬件启动、
PON 注册和网络稳定性验证通过。本轮不连接、重启、刷写或修改光猫。
