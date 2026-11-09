# XG2010G：TAG 桥接规则探测与透明降级

本分支按最终选择采用普通 TAG 透明桥接策略：ONU 的 nft 过滤／专用 flowtable
不可用时允许继续桥接，并公开说明降级状态。full、filter 都被拒绝不再使 TAG 模式切换中止。
这条降级只用于 TAG；UNTAG 规则、离开桥接和 zone 参照清理保持原样。

补丁位于 `patches/feeds/onu_config/luci-app-onu/100-probe-bridge-nft-fallback.patch`，
基于 naoki66 **公开** `OpenWrt_ONU_CONFIG` r26，固定 commit
`3cb13560459f1d51136dac662baa1f399028b2b4`，没有使用或参照发布固件中的脚本。
**naoki66 公开 OpenWrt_ONU_CONFIG r27 以上的版本时，要重新评估这个补丁是否还需要。**

## 核心支持的时间点

naoki66 的旧核心没有 bridge 协定族 flowtable，full 会一直被拒；这个结论不能沿用到
pbs05/ponwrt。迁移后的 pbs05 核心提供 `nf-flowtable-7`，模块和设备就绪时应接受 full。
同属 Linux 6.18 不代表补丁能力相同。

开机 `START=18` 时 netifd 尚未创建 `ct-wanup`，full 仍可能因设备不存在而失败。
filter 使用接口名称匹配，不要求这个设备已经创建，因此能先安装。

## TAG 的三个结果

TAG 中 `ct-wanup` 是 `pon0.<运营商 VLAN>` 的命名设备；它和选中的 LAN 口加入
`br-wanup`。下游路由器接收到不带这个业务 VLAN 标签的帧，管理网络仍在 `br-lan`。

| 文件首行的 ruleset | 本脚本安装的内容 | 处理结果 |
| --- | --- | --- |
| `full` | 原有 EtherType 过滤、zone、`wanup_ft` | 优先使用 |
| `filter` | 原有 PPPoE／可选 IPoE 过滤，没有专用 flowtable | full 拒绝后使用 |
| `unfiltered` | 只有说明注释，没有 ONU nft 对象 | full、filter 都拒绝后的 TAG 透明降级 |

前两种规则文本没有改动。unfiltered 只是不安装本脚本的过滤／卸载表；系统的常规
`inet fw4` 防火墙和其他组件的规则仍存在。不能因此宣称硬件卸载已经生效。

切换到 unfiltered 时，正常重载 firewall4 后会检查并删除 **仅本脚本拥有的**
`table bridge wanup`。仅换成注释文件不会自动删除旧表，旧白名单可能继续阻挡新端口，
因此这一步是 TAG 降级必需的处理，不涉及离开桥接或其他 zone 的清理。
普通 apply 遇到删除失败会返回非零、不写成功 stamp，也不请求 netifd reload。
reprobe 则记录 load_failed 并保留下次重试，沿用不阻断后续 hotplug 脚本的返回方式。

## wan 上线后的探测

`root/etc/hotplug.d/iface/99-internet-bridge-nft` 仅在 `wan ifup` 调用
`internet-apply reprobe`。该路径只处理 nft／firewall4，不 reload netifd：

- 设备就绪后，从 filter 或 unfiltered 升级到 full，并重载一次防火墙。
- 已有合法 full 文件、成功 stamp 且内容一致时，后续 ifup 不再 reload。
- 仍无法安装 full/filter 时保持 TAG 的透明降级；已确认的 unfiltered 也不会重复 reload。
- reload 成功、所需旧表清理成功后，才保存与规则文件完全相同的加载 stamp。

开机仅写入文件时不能标记成“已加载”。独立的 firewall 启动也不会替本脚本补 stamp；
首次 reprobe 会进行必要的 reload／确认。

## 状态文件与 UCI

用户可读取 `/var/run/internet-apply.status`，例如：

```text
requested_mode=bridge
transparent_mode=tag
ruleset=unfiltered
phase=applied
warning=bridge_rules_rejected
nft_error=...nft -c 的单行错误...
```

- `phase=staged`：开机路径完成配置生成，尚未由本脚本确认防火墙加载。
- `phase=loaded`：防火墙 reload、必要的旧表清理和 stamp 写入成功。
- `phase=applied`：普通 apply 还成功提交了 netifd reload 请求；不代表光链路已经上线。
- `phase=load_failed`：防火墙加载、旧表清理或 stamp 失败，不能当作已生效。
- `warning=none` 对应 full；`bridge_flowtable_rejected` 对应 filter。

状态以同目录临时文件、0644 权限和原子重命名发布。无法写入时记录日志，不因观测文件
故障中断可用的 TAG 桥接。它是最后一次 TAG 操作的快照，不是实时模式查询；本次不添加
离开桥接时的状态清理。状态路径在 `/var/run`，不跨重启保留。

UCI 保留用户请求的 `onu-internet` bridge 模式；透明降级会继续生成、应用相应网络拓扑，
无需把模式回写到旧值。补丁不 `set/commit onu-internet`，因此不会重新触发该包的 procd
reload 监听。其他已有 I/O／服务加载失败并非跨 UCI 与内核的原子事务；应结合 phase、
返回码、日志及实际接口状态判断，不能只读页面上的请求值。

## TAG 桥接设置与故障排除

1. 留一个管理 LAN 口在 `br-lan`，例如电脑接 lan4；不要把所有端口都交给业务桥。
2. 在 ONU 的 Internet 页面选择桥接、TAG，填写运营商 Internet VLAN，选择给下游 WAN 的
   LAN 口。下游路由器配置 PPPoE 账号；这个业务 VLAN 由 XG2010G 处理，下游不重复打标签。
3. 如果业务使用 IPoE，应启用页面已有的 IPoE 选项；full/filter 模式保留 r26 原来的白名单。
4. 保存后检查：

```sh
head -1 /etc/internet.nft
cat /var/run/internet-apply.status
logread -e internet
nft list flowtables
```

full 表示可进一步核对 `wanup/wanup_ft` 和 PPE 命中；filter 表示当前没有 ONU 专用卸载；
unfiltered 表示 TAG 已允许透明转发、ONU 白名单和专用 flowtable 未安装。
这两个降级状态都不等于光口已经注册，也不保证线路能拨号或达到硬件卸载吞吐。
仅 ONU bridge 规则可选；普通 firewall4 reload 仍必须成功。若连注释文件也无法校验，
或全局防火墙加载失败，仍返回非零，不把 nft 工具／整机防火墙故障掩盖成成功。

有 `load_failed` 或命令返回非零时，先查同一次日志中的 firewall／nft／stamp 错误。
无论哪种规则，管理电脑应仍能从留下的管理口访问 LuCI。

## 刷机验证清单

- TAG 下游拨号、DNS、双向流量和 PPPoE 大包；保留管理口验证 LuCI。
- 开机后、wan 上线后分别记录文件首行、状态文件和日志。设备尚未出现时允许先 filter；
  上线后应升级 full。重复 ifup 不应重复 reload 防火墙，不能由 hotplug 再 reload netifd。
- `nft list flowtables` 核对 ONU 表与全局 fw4 表；从 PPE debugfs 核对真实硬件卸载。
- 按下面的方法故意拒绝 full/filter：仍应保持 TAG 桥接，状态为 unfiltered，旧
  `bridge wanup` 表消失，LuCI 和普通防火墙正常。恢复后 reprobe 应升回 full。

### 在已生效 TAG 桥接上注入探测失败

在有管理口的测试设备上执行。ONU 包硬依赖 `kmod-nft-bridge`，直接删除它可能连带影响
ONU／IPTV 包；这里仅给一次 reprobe 使用 wrapper，不替换系统 nft，不修改内核模块。

```sh
REAL_NFT=$(command -v nft)
export REAL_NFT
probe_dir=$(mktemp -d /tmp/onu-probe.XXXXXX)
cat > "$probe_dir/nft" <<'WRAPPER'
#!/bin/sh
if [ "$1" = -c ] && [ "$2" = -f ]; then
    case "${3##*/}" in
        internet.nft|internet.nft.*)
            if grep -Eq '^# internet-apply bridge ruleset: (full|filter)$' "$3"; then
                echo 'test: rejecting ONU bridge rules' >&2
                exit 1
            fi
            ;;
    esac
fi
exec "$REAL_NFT" "$@"
WRAPPER
chmod 755 "$probe_dir/nft"
PATH="$probe_dir:$PATH" /usr/libexec/internet-apply reprobe
cat /var/run/internet-apply.status
head -1 /etc/internet.nft
nft list tables
rm -f "$probe_dir/nft"
rmdir "$probe_dir"

# 恢复真实探测；应升级 full，并写入对应 stamp。
/usr/libexec/internet-apply reprobe
```

此实验选择 reprobe 是为了不触发新的 netifd ifup；对普通 apply 仅做一次环境注入后，
后续真实 ifup 可能立刻使用正常 nft 升级 full，这是恢复逻辑的预期行为。
