# ponwrt 基底迁移审查记录

分支：`codex/ponwrt-base`，从指定的 `5d0f942350` 新建。
一次性合并 `pbs05/ponwrt@d9dd3a49f7bb7661c01e9c57c9e2aac2a1114b3e`，
共同祖先为 `2248ed75465327b4eed0ffcc3ece361dc1e62d75`。
本次新增提交的 author/committer 均为 GitHub 账号 `xiaoshao9704`。
没有修改 main、改写历史或推送。

**尚待完成**：feed 选择、最终 seed 清理/提交、用户确认后推送及两份完整固件 CI。
当前两份原始 seed 和五项额外 feed 未改写。下文配置比较针对本地临时生成结果，
不是已经打包到映像中的套件清单。

完整路径、源码来源和两份配置的包名列表见 [机器可读审查记录](ponwrt-base-audit.json)。

## 提交拆分

以下为文档提交之前的实现提交；本文档和审查数据另作一笔提交。

| Commit | 主题 |
| --- | --- |
| `1166c6877a` | merge: adopt pbs05 ponwrt as the XG2010G upstream |
| `c9c82b3470` | airoha: retain public XG2010G CPU, port and ToD support |
| `806b888a90` | airoha: adapt PPPoE egress frame accounting to ponwrt |
| `b2ac37a0a1` | airoha: preserve the public XG2010G voice stack on ponwrt |
| `f29b71472d` | xg2010g: retire XR1710G profiles and unused wireless packages |
| `98ee78b06e` | kernel: refresh inherited patch contexts for Linux 6.18.60 |
| `57610ca444` | xg2010g: discard unused naoki wireless and other-target deltas |
| `eae07325a5` | xg2010g: follow ponwrt runtime defaults and drop unused Wi-Fi data |
| `a80b78851a` | network: distinguish retained PPP and firewall4 fixes from ponwrt builds |
| `3ff2719efc` | feeds: avoid the pinned squeezelite FFmpeg Kconfig dependency cycle |
| `57d2c4ad41` | xg2010g: retain the selected Lucky package removed by ponwrt |
| `e3823cbc08` | ci: verify ponwrt bridge, PON and CPU build artifacts |
| `a02b4137dc` | build: derive upstream revisions from ponwrt |

## 31 个显式冲突

以 ponwrt 为主要基底；保留项目级 XG2010G profile、升级保护和明确要求保留的修复。
libffi 仅使用 ponwrt 的那份。PPP 使用其新版源码和 ujail 脚本，另外保留 PR #638
及 syncdial；版本为 r8。firewall4 版本为 r3。

| 文件 | 最终处理 |
| --- | --- |
| `README.md` | 重写为 XG2010G/ponwrt 关系、升级及验证文档。 |
| `feeds.conf.default` | 保留固定官方 feed、app_airoha、r71 专用驱动 fork 和 ONU 公共 commit；五项额外 feed 暂待确认。 |
| `package/libs/libffi/Makefile` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `package/network/config/firewall4/patches/001-add-bridge-flowtable-support.patch` | 保留 fork 的能力探测及透明桥接 resolver；resolver 与 ponwrt c3b518baec 的行为一致。 |
| `package/network/config/qosify/Makefile` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `package/network/services/dnsmasq/Makefile` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `package/network/services/odhcpd/Makefile` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `package/network/services/ppp/Makefile` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `package/network/services/ppp/files/50-ppp-secrets-mode.sh` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `package/network/services/ppp/files/ppp.sh` | 以 ponwrt 新版 ujail 脚本为底，保留 fork 安全的 syncdial 并发拨号处理。 |
| `package/system/procd/Makefile` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `target/linux/airoha/an7581/base-files/etc/board.d/01_leds` | ponwrt 加 XG2010G 两种 UBI 别名；XR 分支移除。 |
| `target/linux/airoha/an7581/base-files/etc/board.d/02_network` | ponwrt 加 XG2010G 四个 LAN 的原有定义/别名；XR 分支移除。 |
| `target/linux/airoha/an7581/base-files/lib/upgrade/platform.sh` | ponwrt 加 XG2010G 原有 UBI 布局检查、备份和升级保护。 |
| `target/linux/airoha/base-files/etc/board.d/03_pon_data` | ponwrt 加 XG2010G 的 PON 数据/校准处理及别名。 |
| `target/linux/airoha/dts/an7581-nokia_xg-040g-md-common.dtsi` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `target/linux/airoha/dts/an7581-nokia_xg-040g-tf-common.dtsi` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `target/linux/airoha/dts/an758x-nokia_xg-040g-common.dtsi` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `target/linux/airoha/dts/an758x-nokia_xg-040g-stock-parts.dtsi` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `target/linux/airoha/dts/an758x-nokia_xg-040g-ubi-parts.dtsi` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `target/linux/airoha/image/an7581.mk` | 保留 ponwrt 其他机型；以原 XG2010G 两个 compat 2.0 UBI profile 替换重复的普通 XG profile。 |
| `target/linux/airoha/image/an7583.mk` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `target/linux/airoha/patches-6.18/194-v7.2-net-airoha-add-LRO-offload-support.patch` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `target/linux/airoha/patches-6.18/310-10-net-airoha-add-phylink-support.patch` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `target/linux/airoha/patches-6.18/310-11-net-airoha-disconnect-PHY-after-QDMA-teardown.patch` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `target/linux/airoha/patches-6.18/608-net-pcs-airoha-add-AN7581-PON-line-modes.patch` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `target/linux/airoha/patches-6.18/920-16-net-airoha-Account-for-L2-overhead-in-PPE-MTU-configuration.patch` | 删除旧 920-16；采用 ponwrt 190，再单独移植改写后的 920-17。 |
| `target/linux/airoha/patches-6.18/922-net-airoha-add-AN7581-PON-data-and-control-paths.patch` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `target/linux/airoha/patches-6.18/925-net-airoha-add-PON-PPE-offload-metadata.patch` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `target/linux/airoha/patches-6.18/980-revert-fraglist-gro-by-default.patch` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |
| `target/linux/generic/pending-6.18/737-02-net-phylink-introduce-internal-phylink-PCS-handling.patch` | 采用 pbs05/ponwrt d9dd3a49f7；需要的上下文整理另见 refreshed_contexts。 |

## 静默重复和补丁范围

旧编号删除，右侧统一采用 ponwrt 实现：

| 删除的旧补丁 | 采用的 ponwrt 补丁 |
| --- | --- |
| 923-01 / 923-02 | 188 / 189 |
| 182 / 9994 | 192 / 930 |
| 747 | 743 RTL8261 in-band control |
| 920-12 | 193-03 |
| 916-02 HW GRO | 194 LRO |
| 920-16 | 190 |
| naoki generic 675-01..07 | pbs05 generic 675-01..14 |
| 9999-12 | 675-09 |

保留公开 naoki 补丁：0401、0402、201、202 AFE、204、625、628、629、
743 optional SerDes restore、744、910-02、920-17、ToD 920-xg2010g-pon-19、990-01。
原作者和补丁说明均保留，来源记录于各主题提交。

`910-02` 虽然名字包含 USB/PCIe，但 XG2010G 的 lan3 EN8811H 使用已启用的
`usb_pcs`，需要这条时钟路径，故保留。
`920-17` 改用 `test_bit(AIROHA_DEV_F_PON, ...)` 和
`airoha_ppe_set_xmit_frame_size()`：按运行中、相同 QDMA 的设备聚合完整 L2 长度；
LAN 按 VLAN 以太头计，PON 再加 8 字节 PPPoE session 开销，保留新核心的寄存器掩码及打包逻辑。

不移植旧厂商兼容层 920-xg2010g-pon-17/18/20、XR 专用 9990/9993/9999-11/914/914b。
明确移除 phase1 合入的 630 和 mt76 9995。
crypto testmgr、dsa_bridge_ports 等上游不同补丁未按相似 Subject 错删。

14 份补丁只整理上下文以取消 fuzz：generic 675-03/04/11、737-05，
Airoha 130、310-09、604-01、606、608、629、744、748、915-01、990-01。
完整文件名和最终有序补丁集 SHA256 在 JSON 记录中。

## 机型、语音和清理

两份 XG2010G DTS 与旧分支逐字节相同，保留 OPP/SMCC、direct PLL、powersave
启动参数、PHY reset-before-id-read、ToD/PCM/SLIC。
两个原 UBI profile 的 compat 2.0、别名、消息、分区布局及 FIT 保护保留；
移除重复的普通 XG2010G profile。
共享 an7581.dtsi 的 AFE 寄存器窗口、reset 和 sound-dai 定义与语音补丁配套保留。
语音两包及修正后的源码 hash 继续使用。

XR 配置、两份 DTS、CI 选项/默认值/tag 分支、专用板级和升级/envtools 分支已删除。
只给 XR 使用且两份 XG 配置没有选中的 mt7996-board、MLO、clientstatus 系列已删除；
rtl8812au-ct 原本就不存在。删除了未选用的 MT7996 NPU 覆盖固件和 Wi-Fi feed 补丁。
其他无线栈、非 XG 目标和 DHCP/IPv6/LED/sysctl 默认设置采用 ponwrt，减少 naoki 专用差异。

W1700K 的 DTS 和 U-Boot 999 **保留 ponwrt 的版本**；上游仍构建
`an7581_gemtek_w1700k`，不能按 XR 残留删除它们。
`11-xr1710g-cpufreq-defaults` 文件名保留，仅含 XG ondemand/max 1400000 部分。

## feed 和配置发现

任务给定的两项事实与实际代码不同，处理如下：

1. **ponwrt 已删除 Lucky**（96e54770f6），因此恢复公开 naoki 包，保留 2 GiB 所选功能。
   验证 ARM64 下载可用且确为 AArch64 ELF，init/arch 脚本语法通过；完整 LuCI/包集成待 CI。
2. **pushbot 有一个 =y 翻译选项**，但 1 GiB 没选主包，defconfig 自动丢弃它。
   尚未删除五项 feed 或改写原 seed，等待用户决定：清除无效翻译并删除五项 feed，
   或启用主包/翻译并只保留 pushbot feed。

2 GiB 原本已选 Passwall；官方 luci 提供它。helloworld 中十个重叠已选包
（chinadns-ng、dns2socks、ipt2socks、microsocks、两个 shadowsocks-rust、
 simple-obfs-client、tcping、v2ray-plugin、xray-core）均可由官方 feeds 提供。
easyTier、两个 bandix feed 没有独占的已选包。
`pon_drivers` 远端分支已确认停在固定的 fec6b02，ONU 仍是公开固定 3cb1356。

官方 distfeeds 白名单仍是 packages/luci/routing/telephony/video（另有 base/core）。
此清单本来与 ponwrt 官方 feeds 相符，不需换成自定义 feed 名；`check-distfeeds.sh`
已重验通过。构建 feed 与运行时下载地址保持分离。

固定 packages feed 的未选用 squeezelite-custom 有 FFmpeg 传递依赖循环。
新增一个小 feed 补丁，沿用 FFmpeg 自己独立配置菜单的方式；修正后两份 defconfig
不再出现 Kconfig error。仍有未选用 bmx7、video 等包的依赖扫描警告，未据此声称整仓可构建。

### 临时生成配置的差异

“327 / 413”其实是 `CONFIG_PACKAGE_*=y` **符号数**，还包含 tar、dnsmasq 和代理子选项，
不能直接称为映像实际套件数。JSON 分别记录符号及有效包定义的列表。

| 从 =y 消失的符号 | 范围 | 原因 |
| --- | --- | --- |
| kmod-iptables | 两份 | 旧名字不存在；现行已选 kmod-ipt-core/子模块覆盖该功能 |
| kmod-nf-log6 | 两份 | 独立包不存在；已选 kmod-nf-log/NF_LOG_SYSLOG 覆盖 IPv4/IPv6 |
| luci-app-argon-config | 两份 | 已并入 luci-theme-argon，主题 PROVIDES 该名并含配置页面 |
| luci-i18n-zerotier-zh-cn | 仅 1 GiB | 未选主包的孤立翻译；2 GiB 主包及翻译均保留 |
| luci-i18n-pushbot-zh-cn | 仅 1 GiB | 未选主包的孤立翻译；尚待确认，不擅自改 seed |

其余有效已选包保留，包括 Lucky、语音及 IPTV。
2 GiB 的 full sing-box 自动要求 libcronet（隐藏 def_bool），这是保留已选 full 包的依赖，
不换成 tiny 以规避。新出现的 Passwall SmartDNS 默认已关闭，避免额外启用功能。
未启用的 SSR Plus 的 HTTP proxy 默认也临时关闭，避免仅凭残留子选项带入 3proxy；
最终 feed 删除/seed 整理后应移除这些孤立子选项。

## 本地验证与范围

| 检查 | 结果 |
| --- | --- |
| Linux 6.18.60 压缩包 SHA256 | 3c2f44ef6acc021a7ad444d9a2e6ec1ef488ff09368793d0004a6080f69d621e |
| 干净源码重放补丁 | generic 592 + Airoha 186 = 778，全部 fuzz=0 |
| aarch64 编译 | Ethernet、PCS、CPU 电源域、netfilter、bridge、sound/soc 全部成功 |
| 额外 aarch64 对象 | ToD、pinctrl、clk-en7523、Realtek PHY，以及 r71 前端/xPON 成功 |
| 两份 DTS | 预处理、dtc 和 1.4 GHz/SMCC/direct PLL 检查通过 |
| bridge alias | 实际编译 nf_flow_table_inet.o 的 modinfo 含 nf-flowtable-7 |
| PPP / fw4 包补丁 | 全部 fuzz=0；PPP #638 在原 2.5.4 未包含，故保留 |
| feed 补丁 | 8 份严格检查通过，包括未改变内容的 ONU 100 |
| profile isolation / distfeeds | 本地两份生成配置及实际本地 kernel .config 检查通过 |
| 固件 CI / 完整映像 | 尚未执行，需先确认推送 |
| 实机 | 尚未执行；清单见 README |

核心使用 target/linux/generic/config-6.18 + an7581/config-6.18 合并生成的配置，
并打开所选 bridge/netfilter/ToD 模块选项。使用 GCC 14.2.0 的 aarch64 交叉工具链。
实际 CPU 电源域路径为 `drivers/pmdomain/mediatek/airoha-cpu-pmdomain.o`。
以上是目录/对象编译，不是完整 vmlinux、外部模块 modpost 或固件打包。

补丁重放的覆盖文件包括 generic/files 和 airoha/files-6.18（ToD C 文件），
再依 backport → pending → hack → Airoha 的字典顺序，以 `patch --fuzz=0 -p1` 套用。
实际编译时同样有 ToD 覆盖文件；初次审查脚本遗漏 versioned overlay 的记录已在本步骤补齐。

原有回归入口（PPP source 是已套完包补丁的源码，其余两个 shell 文件是固定版本原始文件；
推送测试需要包含 b7189ea 和 fec6b02 祖先的完整 driver Git 历史，浅克隆 feed 不满足此条件）：

```sh
python3 tests/test_ppp_script_child.py --source /path/to/prepared-ppp-2.5.4 -v
python3 tests/test_onu_bridge_nft.py --onu-source /path/to/pristine-internet-apply --fw4-source /path/to/pristine-fw4 -v
python3 tests/test_pon_recovery.py --source feeds/pon_drivers -v
python3 tests/test_phase1_push.py --pon-source /path/to/full-driver-history -v
```

PPP 5、ONU/fw4 27、PON 6、push 6 个测试方法全部通过；PON 内含 29 个生产路径断言及
5 个负对照，push 有 19 个场景。硬件/I2C/nft/远端均使用替身，不能代替设备测试。
新增 CI 产物检查器另用真实本地对象/DTB 加明确的假 manifest 做了两个正例和两个负例；
这只证明检查器行为，不能视为 CI 已编出映像。

## 推送后的必做验证

用户确认后推送当前分支，分别 dispatch 2010.config 和 2010-2g.config，release_type=none。
CI 检查器要求实际 .ko 中有 nf-flowtable-7，实际 DTB 包含 1.4 GHz/SMCC，manifest 中是
r71，并保存生成配置、PPPoE frame-size C/反汇编及映像实际包名列表。
再将两份 manifest 与旧构建的实际 manifest 比较；当前公开旧 release 只有 buildinfo/ITB，
没有 manifest，不能把 seed 清单冒充旧映像实际清单，也不从固件提取文件来凑比较。

实机重点是 compat 2.0 升级、fw4 与 ONU 两个 bridge flowtable 共存和 PPE 命中、
所有 PON 制式、EPON 两阶段恢复、四口吞吐、语音、IPTV 及 CPU 温度稳定性。
UNTAG 外层 EtherType 问题本次仅记录，等待公开新版 ONU。

## 相对 ponwrt 的长期差异

- 两个 XG2010G UBI profile、DTS、升级/envtools/板级别名、CPU 默认策略。
- 上列 14 个公开内核补丁、ToD 覆盖文件/包、voice 两包及目标 sound/DMA 配置。
- 改写后的 PPPoE MTU、fw4 能力探测/失败传播、PPP syncdial/#638 和独立版号。
- 固定的驱动/ONU/app feeds，本地 Lucky，feed 补丁机制及八份补丁。
- 两份用户配置、中文默认值、构建身份/版本、distfeeds、CI/构建脚本及原有测试/文档。
- feed 额外项和 seed 清理仍待完成；JSON 与 git diff 给出当前全部路径。

以后同步优先采用 ponwrt 的共同修复；当公开上游包含上述补丁时删除本地重复实现。
