# XG2010G firmware — ponwrt base

这是 `xiaoshao9704/ImmortalWrt-for-Gemtek-brightspeed` 的 XG2010G 固件分支。
主上游改为 [pbs05/ponwrt](https://github.com/pbs05/ponwrt)，本次一次性合并
`d9dd3a49f7`，之后从该上游同步。Linux 基线为 **6.18.60**。
naoki66 的公开代码只保留下文列出的 XG2010G 必需差异，不再合并其 master。

**XR1710G 已停止支持**：配置、专用 DTS、升级分支和 CI 入口已移除。
ponwrt 自己支持的其他设备仍保留其上游代码；本仓库 CI 只提供以下两种 XG2010G 配置。

| 设备 | 构建配置 | 镜像 profile |
| --- | --- | --- |
| XG2010G，1 GiB RAM | [2010.config](2010.config) | `gemtek_xg2010g-ubi` |
| XG2010G，2 GiB RAM | [2010-2g.config](2010-2g.config) | `gemtek_xg2010g-2g-ubi` |

默认 LAN 为 `192.168.1.1`，用户名 `root`，初始密码为空，LuCI 默认中文。
本机 PPPoE 和 TAG 桥接是主要使用方式；驱动代码覆盖 GPON、XG-PON、XGS-PON 和 EPON，
不同运营商和光模块组合仍需实机验证。

本轮以 **1 GiB 配置**为验收目标；2 GiB 固件验证留待后续。
迁移状态、逐文件冲突处理、配置差异和验证范围见
[迁移审查报告](docs/ponwrt-base-migration.md)。目前尚未运行完整固件 CI 或刷机。

## 源码和保留的功能

| 来源 | 当前内容 |
| --- | --- |
| pbs05/ponwrt `d9dd3a49f7` | 新的 ImmortalWrt 基底、generic bridge flowtable、Airoha 网络/PON/PCS/LRO、用户空间和 libffi |
| [PON 驱动 fork](https://github.com/xiaoshao9704/openwrt-pon-drivers/tree/xg2010g-merged) `fec6b02eae6ccca8e8313d171102670183224b02` | naoki66/pbs05 合并版，`airoha-xpon` r71，包含 EPON 未 prepare 时重新准备 TX 的修复 |
| [naoki66/OpenWrt_ONU_CONFIG](https://github.com/naoki66/OpenWrt_ONU_CONFIG) `3cb13560459f1d51136dac662baa1f399028b2b4` | 公开 ONU r26，本机拨号、桥接和 IPTV 用户空间；以 `onu_config` feed 取代 `pon_userspace` |
| naoki66 公开固件源码 | XG2010G UBI/升级保护、1.4 GHz OPP、10G/2.5G PHY/PCS、ToD、语音、改写后的 PPPoE MTU 和 FDB 漫游修复 |
| 本 fork | fw4 加载失败传播及能力探测、PPP syncdial/PR #638、UPnP counter、feed 补丁机制、distfeeds、中文 UI、CI 和原有回归测试 |

保留两份配置原来选中的 IPTV、Argon/配置页面、package-manager、NPU、WireGuard、
TUN、CAKE、BBR、cryptodev、fullcone、PPP multilink、shellsync、语音和诊断工具。
2 GiB 配置原本还选中了 Passwall 和 Lucky；Lucky 已从 ponwrt 删除，故保留 naoki66
公开源码中的本地包，避免功能消失。没有新增 BBRv3；如以后需要，应作为单独变更评估。

已删除 easytier、openwrt_bandix、luci_app_bandix、helloworld、pushbot 五项额外 feed。
孤立的 pushbot 翻译项经确认删除；其余重叠包可由官方 feeds 提供。
1 GiB 配置以[实机安装清单](docs/xg2010g-installed-baseline.json)为准：
294 个旧 APK 经两项内核包合并映射为预计 292 个新 APK，没有漏掉现有功能或额外选包。
库的 ABI 换名由检查脚本处理；这仍需用 CI 的实际 manifest 验证。

所有 feed 版本固定在 [feeds.conf.default](feeds.conf.default)。自定义 feeds 仅用于构建，
不会出现在设备的官方 distfeeds URL 中。ONU 修改只通过 `patches/feeds/onu_config/`
应用；原 `100-probe-bridge-nft-fallback.patch` 内容保持不变。
未从任何已发布固件提取代码，也未加入第三方 airoha-manager。

## CPU 默认策略

两份原始 XG2010G DTS 均保留 1.25、1.30、1.35、1.40 GHz OPP 及对应 SMCC 档位，
并启用 `airoha,force-direct-pll`。早期启动参数仍为
`cpufreq.default_governor=powersave`。

首次应用板级 CPU 默认设置时，策略为 **ondemand，最高 1.4 GHz**，并非锁定在 1.4 GHz。
已有明确保存的 CPU 策略会被保留；uci-defaults 文件名
`11-xr1710g-cpufreq-defaults` 不变，以免升级后重复执行。
1.4 GHz 的温度、供电和长期稳定性需要在实际设备上检查。

## 后续同步

只从 ponwrt 合并共同基底。首次在新 clone 中配置 remote：

```sh
git remote add ponwrt https://github.com/pbs05/ponwrt.git
git fetch ponwrt master
git merge ponwrt/master
```

每次合并后重新检查保留补丁和两份配置；自动同步模板仍为 `.disabled`，没有启用定时合并。

## 构建

```sh
./scripts/feeds update -a
./scripts/feeds install -a
FEED_PATCHES_STRICT=1 bash scripts/apply-feed-patches.sh
cp 2010.config .config                 # 2 GiB 改用 2010-2g.config
bash scripts/set-build-version.sh .config
make defconfig
bash scripts/check-distfeeds.sh
bash scripts/check-gemtek-profile-isolation.sh --config .config
make download -j8
make -j"$(nproc)"
```

[GitHub Actions](.github/workflows/build-firmware.yml) 默认构建 `2010.config`；
手动构建使用 `release_type=none` 可只保留构建产物。
本轮先运行 1 GiB 配置；2 GiB 留待后续验证。工作流会检查 profile 隔离，并从实际编译产物确认：
`nf-flowtable-7`、r71 xPON manifest、1.4 GHz/SMCC DTB、PPPoE frame-size 源码及对象。
`ponwrt-verification/` 会随固件上传生成的配置、反汇编、实际包名列表，以及与实机基准的比较。
配置阶段和产物阶段都运行 `check-installed-package-baseline.py`；所有已选包也必须出现在映像 manifest 中。

## 升级

这两个 profile 都保留 `DEVICE_COMPAT_VERSION := 2.0`、原有兼容别名和检查信息，
不同时生成 ponwrt 的另一个 XG2010G profile。
仅适用于匹配的 **XG2010G OpenWrt U-Boot UBI 布局**，1 GiB 和 2 GiB 镜像不能互换。

布局仍是首个 `0x20000` 擦除块中的 `bl2`，随后为含 `factory` 等卷的 UBI；
升级脚本只重建动态 `fit`/`rootfs_data`，保留 `fip`、环境和校准卷。
现有布局检查和 64 MiB FIT 保护保持不变。

先保存配置和必要的原厂备份，然后检查镜像：

```sh
sysupgrade -T /tmp/xg2010g-sysupgrade.itb
```

检查通过后，保留设置升级用 `sysupgrade /tmp/xg2010g-sysupgrade.itb`；
清除设置验证用 `sysupgrade -n /tmp/xg2010g-sysupgrade.itb`。
这条兼容升级路径不需要 `-F`；检查不通过时应先排查布局或机型。

## 桥接建议使用 TAG

TAG 模式由 XG2010G 处理运营商 VLAN，下游路由器在选定 LAN 口拨号。
公开 ONU r26 的 UNTAG 规则只识别外层 EtherType；下游自行加 802.1Q 时，
PPPoE/IPoE 帧可能被过滤而无法拨号。本次不修改这一已知问题，等 naoki66 公开 r27
或更高版本后再评估。

ponwrt 核心支持 bridge flowtable。fw4 会覆盖透明桥接端口，ONU 的 internet-apply
也会为 TAG 上联及指定 LAN 建立 `wanup_ft`。
源码允许同一接口绑定多个 flow block，ONU 链优先序更早；
**两个表同时存在时能否稳定卸载，仍需下面的实机验证**。

## 刷机后验证清单

每次记录固件版本、PON 制式/光模块、运营商 VLAN、测试结果和相关日志。

- **升级**：从当前固件保留设置升级一次、清除设置升级一次，均不用 `-F`。
- **本机拨号**：确认 PPPoE、DNS、UPnP、双拨；从合适的 LAN 主机测试
  `ping -s 1464 -M do <可响应的公网 IPv4>`，确认大包能通过。
- **TAG 桥接**：下游路由器拨号；`head -1 /etc/internet.nft` 应显示 `full` 模式。
  用 `nft list flowtables`、`nft list table bridge fw4`、
  `nft list table bridge wanup` 核对 `fw4/fb` 与 `wanup/wanup_ft`，再从 PPE debugfs
  确认实际流量已卸载，并测试重拨和双向大包。
- **PON**：冷启动五次，记录注册和上线时间；GPON、XG-PON、XGS-PON、EPON 按实际线路分别验证。
  EPON 在线且允许断线时，执行下面两阶段恢复测试；每次等线路恢复后再测下一项。
- **CPU**：检查 `scaling_governor`、`scaling_max_freq` 和负载下的实际频率，确认可达到
  1400000 kHz，并记录温度及稳定性。
- **语音**：电话口拨入/拨出、摘挂机、振铃及 `601` 测试分机；细节见
  [语音调试记录](docs/xg2010g-voice-debug.md)。
- **IPTV**：分别验证 msd_lite、rtp2httpd、udpxy 及现有组播配置。
- **LAN**：四口双向吞吐，重点检查 lan1/lan2 的 10G 协商和 lan3 的 EN8811H 2.5G。

```sh
cat /sys/kernel/debug/airoha-xpon-pon0/mac
echo 1 > /sys/kernel/debug/airoha-xpon-pon0/recover_tx
# 等待线路恢复，查看日志与 burst_rearms/frontend_reloads，再进行第二阶段：
echo 2 > /sys/kernel/debug/airoha-xpon-pon0/recover_tx
cat /sys/kernel/debug/airoha-xpon-pon0/mac
```

`recover_tx` 是 EPON 恢复路径的测试入口；不能用它证明其他 PON 制式的恢复逻辑正常。
测试分别运行 `tests/test_ppp_script_child.py`、`test_onu_bridge_nft.py`、
`test_pon_recovery.py`、`test_phase1_push.py` 和 `test_installed_package_baseline.py`；
所需源码参数和完整验证范围见迁移报告。
