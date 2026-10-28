# XG2010G：ONU 桥接 nft 先探测完整规则，失败再降级

`luci-app-onu` 的 `internet-apply` 在桥接模式写 `/etc/internet.nft`。当前 XG2010G 内核不接受 bridge family 的 flowtable 时，上游脚本的 `nft -c` 会失败并直接退出，整张表都不安装，EtherType 过滤也就没有了。

本仓库用 feed 补丁改这个行为，补丁在
`patches/feeds/onu_config/luci-app-onu/100-probe-bridge-nft-fallback.patch`。
不改 `onu_config` 上游仓库，也不把 flowtable 从脚本里删掉。

## 探测顺序

每次 `internet-apply`（开机 `START=18`，或页面保存）在桥接模式：

1. 生成完整表：`flowtable wanup_ft`（`flags offload`）、`ct zone set 1`、PPPoE（EtherType `0x8863`/`0x8864`）以及按需的 IPoE（`arp`/`ip`/`ip6`）过滤、`flow offload @wanup_ft`。钩子优先级仍是 `filter - 1`。
2. 对这份完整表执行 `nft -c -f`。通过则安装。文件首行是 `# internet-apply bridge ruleset: full`。
3. 不通过则改写为同一套 PPPoE/IPoE 过滤，不含 flowtable、conntrack zone 和 flow offload 语句，再 `nft -c`。通过则安装。首行是 `# internet-apply bridge ruleset: filter`，并记一条 log。
4. 过滤表也不通过则删掉临时文件并失败。不会留下半份规则，也不会覆盖已经在用的 `/etc/internet.nft`。

页面关闭或不是桥接时只写说明，不建表。

下一次 apply 仍从完整表开始。内核以后接受 bridge flowtable 时，同一份脚本会装上完整规则，不需要再改补丁。

## 为什么 `wan` ifup 还要再探一次

`internet-apply` 在 `START=18`，netifd 还没创建 `ct-wanup`。TAG 模式的 flowtable 设备列表包含 `ct-wanup`。设备不存在时 `nft -c` 失败，和内核不支持 flowtable 是同一种结果。这时若把完整表写进文件，firewall4 加载整份规则集会失败。

所以启动时先留下过滤表。`wan` ifup 之后，`/etc/hotplug.d/iface/99-internet-bridge-nft` 调用 `internet-apply reprobe`：

- 只重写 nft 文件，并在规则变化或 stamp 与磁盘不一致时重载 firewall4。
- 不调用 netifd reload，热插拔不会打环。
- 内核仍拒绝 flowtable 时，过滤表保持不变；已成功加载且 stamp 匹配时，不会每次 ifup 都重载防火墙。
- **只有** firewall reload（经公共 `firewall_reload_stamp` / `reload_runtime`）成功后才写“已加载”stamp。reload 失败会清掉 stamp，下一次 `wan` ifup 再试。磁盘上已是合法 filter、只需补 stamp 时走 `ensure_rules_loaded`（只 reload，不传空 staging、不 `mv`），不会盲标记已加载。
- LuCI apply 与 hotplug reprobe 共用 `stage_validated_rules`（full→filter 探测）和一把 `/var/lock/internet-nft-reprobe.lock`，避免探测顺序漂移或并发写 `/etc/internet.nft`。`commit_probed_rules` 在 install 前要求 staging 含 ruleset 头，拒绝空文件覆盖。
- reprobe 要求 bridge 且 `ports` 非空；端口为空时只 warn 并跳过，不写文件。

## 和 `fix/xg2010g-onu-bridge-rules` 的差别

那条分支直接去掉 flowtable、ct zone 和 flow offload。本分支不搬那套删除，完整规则仍是首选。语音包的 hash 改动也不在这里。

## 不会做的事

CI 只产出固件包。不要用这次构建去刷现网光猫。
