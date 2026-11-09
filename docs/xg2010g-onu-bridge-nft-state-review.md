# ONU TAG bridge：加载状态与透明降级验证

## 当前基线和范围

从迁移后的 `codex/ponwrt-base`（`e8bbe9cc6b`）新建
`codex/onu-bridge-failclosed`。按讨论后的最终选择，实际实现是 **允许 TAG 透明降级**：
full/filter 都被拒时允许桥接继续，不采用最初“保持旧模式并失败”的策略。
实现与测试提交为 `f8d6397845`；正常防火墙／网络步骤成功时，该 TAG 降级返回 0，状态明确记为 unfiltered。

输入仅为 naoki66 公开 OpenWrt_ONU_CONFIG r26
`3cb13560459f1d51136dac662baa1f399028b2b4`。没有使用或参照发布固件中的脚本。
**naoki66 公开 OpenWrt_ONU_CONFIG r27 以上的版本时，要重新评估这个补丁是否还需要。**

UNTAG 的规则、拓扑和拒绝策略保持原样；离开桥接、zone 引用清理不在此次范围内。
旧 PR #3 的加载状态修复已经是本分支基线，可从基线文档查看历史审查矩阵。

## 核心能力的变化

naoki66 旧核心不提供 bridge flowtable 的 `nf-flowtable-7`，full 即使等到设备出现也被拒。
pbs05/ponwrt 的核心提供该能力，因此 full 成功加载和 hotplug 升级路径现在必须验证。
开机时另一个独立条件是 `ct-wanup` 尚未由 netifd 创建；这时先 filter 是正常的。

## 文件、内核和确认记录

沿用三个独立状态：

- `D`：`/etc/internet.nft`，候选／已安装文件。
- `K`：内核中的实际 nft 对象。
- `S`：`/var/run/internet-nft.loaded`，本脚本成功 reload 后保存的完整文件快照。

新增 `/var/run/internet-apply.status` 是最后一次 TAG 操作的可读结果，不是 `K` 的实时查询。
文件字段与用户用法见 [TAG 设置及故障排除](xg2010g-onu-bridge-nft-fallback.md)。

| 路径 | 文件与加载行为 | 成功确认 |
| --- | --- | --- |
| 普通 apply，full 首次通过 | 原 full 规则；先 firewall，再请求 network reload | S 与 D 完全一致；phase=applied |
| START=18，ct-wanup 尚不存在 | 先写 filter；启动路径不主动 reload | S 不凭空补写；phase=staged |
| wan ifup 后 full 通过 | 安装 full，仅 reload firewall4 | S=D；phase=loaded |
| full 已确认，后续 wan ifup | 校验磁盘／stamp 后短路 | 不重复 reload |
| TAG full/filter 均拒绝 | 写注释型 unfiltered include，继续普通桥接 | 正常 firewall reload 后清除旧 wanup 表，再写 S |
| unfiltered 以后 full 恢复 | 正常安装 full、reload、更新状态 | 清除旧降级警告；以后不重复 reload |
| 旧 wanup 表删除失败 | 普通 apply 返回非零；reprobe 返回 0 保持 hotplug 链，不请求 network reload | 无成功 S；phase=load_failed |

注释文件本身不会删除旧内核对象。unfiltered 路径用 `nft list tables` 检查，仅在存在时
删除 `table bridge wanup`，不删除 `inet fw4`、`bridge fw4` 或其他表。
这项处理仅属于 TAG 的 full/filter → unfiltered 降级，不扩展离开桥接的清理策略。

保留原有约束：安装前和 reload 前清 stamp；只有 firewall 成功及所需旧表清理成功后才
原子发布新 stamp。状态文件的写失败只记录日志，不让已经可用的桥接因观测失败中断。

`phase=applied` 只表示配置步骤和 netifd reload 请求成功，不证明 WAN 已上线。
`phase=loaded` 也不代表网络模式已切换。其他原有配置／服务失败仍可能发生在 UCI 提交后，
不能据此声称整个操作是跨系统原子事务。

## UCI 与 reload 触发

透明降级中，`onu-internet` 仍保留用户要求的 bridge，生产网络写入器也继续生成
802.1q 的 `ct-wanup` 和 `br-wanup`，因此不需要回写旧模式。
整个改动不 set/commit `onu-internet`；状态只写 `/var/run`，不会重新触发
`/etc/init.d/internet` 的 `procd_add_reload_trigger "onu-internet"`。

hotplug 只接受 `wan ifup` 并执行 reprobe。reprobe 不调用 netifd reload；测试同时约束
配置触发源没有写操作和重复 ifup 没有网络 reload，防止形成 reload 环。

## 测试内容

`tests/test_onu_bridge_nft.py` 当前 **37 个测试方法**：

- 保留原有 27 个方法，继续覆盖 stamp、安装失败、完整文件比较、SIGKILL、fw4 返回码等。
  原“全部拒绝仍失败”的方法在 UNTAG 下保留原断言；TAG 的新策略由整脚本测试覆盖。
- 新增 9 个生产 main／hotplug 场景：有旧表／无旧表的双拒绝、首次 full、开机双拒绝、开机 filter →
  full、unfiltered → full 恢复、旧表删除失败、状态 I/O 故障、UNTAG 原行为。
- 一个负向对照方法执行 **16 个行为突变**。每个变体先通过 shell 语法检查，再要求相应
  正向场景因行为断言失败，不能拿编译／语法错误充当检出。

负向对照包括：拒绝透明降级、跳过拓扑写入、保留旧表、丢失状态、丢失日志、写回
procd 触发源、跳过 stamp、阻止上线后升级、不识别已有 stamp、错误 full 标头、
恢复后留下旧警告、忽略旧表删除失败、hotplug reload netifd、误放宽 UNTAG、状态 I/O 致命化、开机未经 reload 就标记成功。

测试执行真实生产 main、UCI 写入函数、规则生成／安装／确认函数及实际 hotplug 脚本。
平台配置读取和设备存在性检查被替换；UCI、nft、firewall、ubus 写入临时目录模型。
模型刻意保留旧 wanup 表，只有生产代码显式删除才消失，避免把 comment include 的作用模拟错。
没有执行宿主机 nft／网络修改，也没有真实内核收包。

全部 `tests/` 共 **60 个方法**通过：ONU/fw4 37、PPP 5、PON 恢复 6、推送 6、
安装包基准 6。ONU 脚本分别在 dash 和 BusyBox ash 下运行 37 个方法，均通过；
fw4 返回码测试仍用 Bash。16 个行为负向对照在两个 shell 下均检出回归。

## 复现

依赖 Python 3、Git、dash、Bash、flock 和常规 POSIX 工具。firewall4 源码使用本分支固定的
`e6f600c458bda7bc2d87b07e78fd06b50c9d7131`；`999` 错误传播补丁未修改。

```sh
curl -fL https://raw.githubusercontent.com/naoki66/OpenWrt_ONU_CONFIG/3cb13560459f1d51136dac662baa1f399028b2b4/luci-app-onu/root/usr/libexec/internet-apply -o /tmp/onu-internet-apply
curl -fL https://raw.githubusercontent.com/openwrt/firewall4/e6f600c458bda7bc2d87b07e78fd06b50c9d7131/root/sbin/fw4 -o /tmp/onu-fw4
python3 tests/test_onu_bridge_nft.py --onu-source /tmp/onu-internet-apply --fw4-source /tmp/onu-fw4
# 已有 BusyBox 时也可用 ash 执行 ONU 脚本；fw4 测试仍用 Bash。
python3 tests/test_onu_bridge_nft.py --onu-source /tmp/onu-internet-apply --fw4-source /tmp/onu-fw4 --shell 'busybox ash'
```

`--baseline-ref e8bbe9cc6b` 可把新断言用于迁移分支原实现；TAG 新行为和状态的失败为预期。
原始 r26 文件 Git blob 为 `ced2d0305fe5b8692b07cfd8a5c84eb2be94347a`。
补丁在新临时目录对固定原文应用，测试不会使用已改过的 feed 文件作为“原始输入”。

## 验证边界和刷机清单

本地测试不能证明真实 bridge flowtable、PPPoE/IPoE 数据面和 PPE 卸载正常。
当前分支尚未推送，未为本修复触发 CI，也没有刷机或读取真实设备状态。
迁移分支的旧构建不能算本修复的 CI 结果。

刷机后需：

1. 保留管理口，确认 TAG 下游拨号和 LuCI 可用。
2. 开机后、wan 上线后分别记录文件首行、状态、stamp 和日志；验证 filter → full 及后续
   ifup 不重复 reload，first-full apply 也应有正确的成功 stamp。
3. `nft list flowtables` 检查完整表，结合 PPE debugfs 验证流量，而非仅看对象存在。
4. 按用户指南中的 wrapper 注入 full/filter 校验失败：TAG 继续工作、状态 unfiltered、
   旧 wanup 表消失、常规防火墙和管理口可用。恢复真实探测后升级 full。
5. 真实 firewall reload／旧表清理失败时确认返回码和 load_failed，不能把文件已替换当加载成功。

不在此范围：UNTAG 外层 EtherType 的已知问题、离开桥接的清理、zone 参照清理、外部
组件修改内核规则后的持续一致性监控。stamp 仍是本脚本观察到的一次成功，不是内核实时审计。
