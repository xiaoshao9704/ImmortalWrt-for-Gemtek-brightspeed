# Notes (xiaoshao9704 fork)

Vs upstream `2010.config`, packages trimmed to match the live ONT cleanup:

**Not built in**
- Proxy/VPN leftovers: `sing-box`, `zerotier` / `luci-app-zerotier`
- Misc / unused LuCI: `lucky`, `ddns-go`, `luci-app-ddns` (+ `ddns-scripts*`),
  `luci-app-arpbind`, `luci-app-autoreboot`, `luci-app-timewol`,
  `luci-app-ttyd` / `ttyd`, `luci-app-vlmcsd` / `vlmcsd`,
  `luci-app-watchcat` / `watchcat`, `luci-app-wol` / `etherwake`,
  `luci-app-pushbot`
- `mwan3` already unset upstream

**Kept (as on the ONT)**
- VoIP: `asterisk*` / ONU voice
- IPTV helpers: `udpxy`, `msd_lite`, `rtp2httpd` (+ LuCI), `omcproxy`, `igmpproxy`
- UPnP: `miniupnpd-nftables` / `luci-app-upnp`
- `pbr` / `luci-app-pbr` packaged; `99-pbr-disabled` sets `enabled=0` on first boot

No PPPoE secrets. Network defaults unchanged (br-lan + pon0 DHCP).
`sync-upstream` workflow disabled so these choices are not overwritten blindly.
