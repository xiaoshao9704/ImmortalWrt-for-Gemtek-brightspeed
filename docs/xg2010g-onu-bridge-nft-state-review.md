# PR #3：ONU bridge nft 加载状态验证与补丁

## 基线与结论

复核 PR：<https://github.com/xiaoshao9704/ImmortalWrt-for-Gemtek-brightspeed/pull/3>。
**修复状态**：v2 加载状态修复及 27 项回归测试已提交到 PR 分支，见
[`62929827`](https://github.com/xiaoshao9704/ImmortalWrt-for-Gemtek-brightspeed/commit/6292982743f54d40c482d79412ca7da9e08dd85a)。
这里的“已提交到 PR”不表示 PR 已合并到目标分支。

**历史审查基线**：首次调查时 PR 为 Open、包含 5 次提交，HEAD 为
`d2736be1e45dd0f4f74b5b9b31171ef6a72af963`；问题描述最初引用的是两提交版本
`f9fba27aa25da7c057b53e8f5e90100a59e89da4`。以下缺陷分析和对照表中的基线结论指这两个历史版本，不是对修复后 HEAD 的描述。

- `408a924c`、`11c66fe0` 已修掉旧版直接补 filter stamp 的分支，并在 reload 返回失败时清理 stamp。
- `d2736be1` 增加 full 短路；其谓词仍执行一次磁盘文件 `nft -c`，不是完全省略校验。
- 审查基线 `d2736be1` 存在安装失败后继续标记、替换文件后旧 stamp 残留、reload 中断残留及 stamp 写失败被忽略的问题；上述问题已由 v2 修复。
- **更底层的问题**：固定版本的 firewall4 在 nft 加载失败后执行 includes，后者成功会覆盖失败状态。因此，仅修 ONU 脚本的成功分支还不够。

## 三种状态必须分开

`D` 是 `/etc/internet.nft`，`K` 是内核已装载规则，`S` 是本脚本的加载确认记录。
`nft -c` 只校验 `D`；`mv` 只替换 `D`；二者都不能证明 `K=D`。
旧版 stamp 只有 `full` / `filter`，也不能区分同种模式的不同端口或 IPoE 配置。

本补丁维持以下规则：

1. 探测仍依次尝试 full、filter；两者均拒绝，不替换磁盘文件。
2. 安装前处理 chmod 错误、清除旧确认，再原子替换磁盘文件。失败不 reload、不记录目标成功；apply 报错，hotplug 记录警告并留待下次重试。
3. reload 前再次清除确认。失败或进程中断，不能留下旧的成功记录。
4. firewall4 的渲染/nft 管道失败必须返回非零，不继续 includes。
5. reload 成功后将本次文件完整复制到 stamp 同目录的唯一临时文件，再用 mv 原子发布 stamp；创建、复制或重命名失败均视为未确认并清理临时文件。`nft_loaded_is` 用文件模式和 `cmp -s` 判断，旧的单行 stamp 自动触发一次 reload。

使用文件快照避免引入散列工具依赖；当前 `2010.config` 已启用 BusyBox `cmp`。
磁盘更新和内核事务不是跨系统原子提交：reload 失败时允许 `D` 为新规则、`K` 为旧规则，但 `S` 必须为空，以保留下次重试的依据。

## 路径矩阵

| 路径 | f9fba27 的行为 | d2736be1 的行为 | 本补丁 |
| --- | --- | --- | --- |
| START=18 写 filter，START=19 未成功加载，首次 WAN ifup 仍拒绝 full | `reprobe_bridge_nft` 直接写 filter stamp，K 可能为空 | 通过 ensure helper reload；明确失败则无 stamp | 保留重试，并修复 fw4 可能假成功的问题 |
| `commit_probed_rules filter` 遇到已存在的合法 filter、缺少匹配 stamp | 另一处直接写 filter stamp | 已删除盲标记逻辑 | 保持先 reload 再确认 |
| full 降级 filter，首次 reload 失败，下一次 ifup 仍只能 filter | 磁盘已换，下一次直接标记 filter，跳过重试 | reload 返回非零时会清 stamp 并重试 | 失败码传播正确后可靠重试 |
| filter 升级 full，首次 reload 失败，原本没有 full stamp | 通常会重试 full；不能把所有升级路径都称作失败 | 会重试 full | 保持此行为 |
| 原有 full stamp，降级失败，再升级失败，再 ifup | 旧 full stamp 没清，磁盘又是 full，可能直接跳过加载 | 明确失败时已清 stamp，修正此往返问题 | 同时覆盖中断、fw4 假成功 |
| `mv` 失败，但 firewall reload 返回 0 | 可能给旧磁盘/内核规则标记目标模式 | 同样未检查 install 返回值 | 不 reload、不标记目标，清理 staging |
| chmod 失败但 mv 成功 | 继续安装 | 继续安装 | 中止安装并保留原文件 |
| 同模式文件已替换，后续 network/firewall UCI 步骤中止 | 旧模式 stamp 可能误匹配 | 仍可能误匹配 | 安装即撤销确认；内容比较也拒绝同模式不同内容 |
| reload 过程中进程中断 | 旧 stamp 可能残留 | 直到失败分支才清理，仍有窗口 | 调用 reload 前清除 |
| nft 或规则渲染失败，随后 includes 成功 | fw4 返回 0，ONU 可误标记 | 同样存在 | fw4 管道后 `|| return 1` |
| stamp 写入失败 | 成功返回可能掩盖错误 | 同样忽略写 stamp 返回值 | 不报告成功确认，下次重试 |
| filter/full 已确认、磁盘内容未变 | 按模式跳过 | 按模式跳过 | 按完整文件快照跳过，保持避免重复 reload 的设计 |

## firewall4 错误码证据

仓库 `package/network/config/firewall4/Makefile` 固定版本为
`b6e5157527d361f99ad52eaa6da273cb0f2dfd59`。
该版本 [root/sbin/fw4](https://github.com/openwrt/firewall4/blob/b6e5157527d361f99ad52eaa6da273cb0f2dfd59/root/sbin/fw4) 的 `start()` 连续执行：

```sh
ACTION=start utpl -S $MAIN | nft $VERBOSE -f $STDIN
ACTION=includes utpl -S $MAIN
```

虽有 `set -o pipefail`，但没有 `set -e` 或显式判断；第二条命令覆盖第一条管道状态。
审查基线 `d2736be1` 的 firewall4 patches 未修正该位置。init 的 `reload_service()` 直接调用 `fw4 reload`，
本仓库 rc.common 的 reload 路径将这个返回值向上传递。新增的 package patch 只在第一条管道后增加 `|| return 1`。

测试直接运行这个固定版本的 fw4（临时路径，Bash 驱动），用假的 `utpl`/`nft` 注入
渲染失败、加载失败、includes 失败和全部成功，验证退出码及失败后 includes 未执行。
这不等于运行真实 nft/netlink，也不等于验证 BusyBox ash 固件。

## 回归测试与复现

测试文件：`tests/test_onu_bridge_nft.py`。依赖 Python 3、Git、dash、Bash、flock 和常规 POSIX 工具。
它在临时目录对真实固定版本源码应用 patch，再执行生产脚本函数；只替换系统入口、服务调用及 nft 外部命令。
不会执行宿主机 `/etc/init.d/firewall`，不会联网或触碰设备。模拟内核文件仅是预期规则快照，不是内核观测。

先获取未打补丁的源码（或从相应固定版本 checkout 复制）：

```sh
curl -fL https://raw.githubusercontent.com/naoki66/OpenWrt_ONU_CONFIG/3cb13560459f1d51136dac662baa1f399028b2b4/luci-app-onu/root/usr/libexec/internet-apply -o /tmp/onu-internet-apply
curl -fL https://raw.githubusercontent.com/openwrt/firewall4/b6e5157527d361f99ad52eaa6da273cb0f2dfd59/root/sbin/fw4 -o /tmp/onu-fw4
python3 tests/test_onu_bridge_nft.py --onu-source /tmp/onu-internet-apply --fw4-source /tmp/onu-fw4
```

本次输入的 Git blob hash 分别为 `ced2d0305fe5b8692b07cfd8a5c84eb2be94347a`、
`d9ac8a19fb6247661b5b8bc73e8c73fb91c6b826`。
首版补丁的 23 个测试方法对照 `d2736be1` 得到 13 个失败断言/子场景，对照 `f9fba27` 得到 21 个；不是 13/21 个独立测试方法。补丁版无失败。

添加 `--baseline-ref d2736be1` 或 `--baseline-ref f9fba27` 可对原实现运行相同断言；失败是预期对照结果。
`--shell 'busybox ash'` 可在安装了 BusyBox 的环境补跑 ONU 测试；fw4 测试仍使用 Bash。

## 验证边界

- **本地模拟**：优化版 27 个测试方法，含多个子场景；补丁版全部通过。覆盖首次启动、两处旧 filter 盲标记、双向切换、连续失败、失败后重试、同模式配置变化、安装与标记 I/O 失败、中断、空 staging、空端口、禁用/路由模式、TAG/UNTAG、过滤内容与 full 优先顺序。另执行补丁应用校验和完整脚本语法检查。
- **CI 固件构建**：首次调查按基线 `d2736be1` 查询 check runs、全部触发类型的 workflow runs、commit statuses，均未返回记录；该结果只是历史查询快照，不代表后续 HEAD 的 CI 状态。本轮修复工作没有触发新构建。现有 build workflow 只接受 `v*` tag 或手动 dispatch，PR 本身不会自动执行该固件构建。旧提交的构建不能证明本次 HEAD 或本修复通过。
- **真实 XG2010G**：未接触、未刷写、未运行网络命令；bridge flowtable、PPPoE/IPoE 数据面、硬件 PPE offload 均未验证。

成功 stamp 表示“本脚本观察到 firewall reload 成功且保存了这份文件”，不是持续监控内核。
本修复依赖正常启用的 firewall nftables include；外部删除/冲刷表、绕过本锁改配置、禁用 include，
或其他组件在成功后改写内核规则，不能仅靠 stamp 被完整识别。`nft -c` 通过也不证明数据流已进入硬件。
没有把这些范围宣称为已完成的内核一致性或硬件验证。

后续应先对这个确切补丁提交构建 `2010.config`（不发布、不刷现网），核对构建产物中的 ONU 脚本及 fw4 错误传播补丁。
仅在独立实验设备上采集首次启动、每次 ifup 和故障前后的 `/etc/internet.nft`、stamp、
`nft -a list table bridge wanup`、fw4 日志与返回码；检查过滤规则、zone、flowtable 对象及计数器。
full→filter 时还应检查旧 flowtable 对象是否残留；此补丁保留现有 nft 渲染语义，不对真实内核对象清理作保证。
最后再验证 PPPoE 建链、IPoE 放行/隔离与 PPE entries。构建成功和 nft 校验成功均不能替代这些测试。

## r5 审查后优化（v2）

- **R5-N1 已处理**：`nft_mark_loaded` 采用同目录 `mktemp` → `cp` → `mv -f`；正式 stamp 只在快照完整后可见。创建/复制/重命名错误均返回失败，普通失败清理临时文件。SIGKILL 无法执行清理，可能留下未发布的临时文件，但匹配逻辑不会读取它；下一次调用仍可正常确认。此改动保证原子可见性，不声称断电持久化。
- 新增复制中途的可见性断言、mktemp/cp/mv 故障注入，以及真实 SIGKILL 测试进程后重新调用的验证。优化版共 27 个测试方法，全部通过；同一套新增断言对首版补丁能检出未原子发布的问题。
- **R5-N2 已证伪**：`reload_sets()` 的管道是函数末尾命令，`pipefail` 的非零状态不会被后续命令覆盖。保持生产代码不变，加入四组测试：`(utpl,nft)=(0,0),(0,7),(9,0),(9,7)`，退出码依次为 `0,7,9,7`。
- **R5-N3 为预期的全局变化**：新增 fw4 patch 作用于全机 start/reload，渲染或 nft 加载失败将跳过 includes 并返回非零；其他调用方也会观察到这个正确的失败状态。实验机仍需验证真实退出码和 includes 行为。
- v2 补丁包验证完成时的远端基线为 `d2736be1e45dd0f4f74b5b9b31171ef6a72af963`；随后已通过 `62929827` 提交到 PR 分支。修复工作未合并 PR、未触发固件构建、未进行实机操作。
