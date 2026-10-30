# XG2010G cryptodev image

Enable kmod-cryptodev and libopenssl-devcrypto in both XG2010G seeds,
carrying forward the two selections tested as configuration in experimental
commit d93c548348c04d1ccae7528b1cff1899deb2d2c8. Keep the stable PPP
2.5.4-r3 fix and omit pbr. Require both crypto packages in the existing
config and image-manifest checks.

Use the packaged OpenSSL engine configuration without changing its cipher
policy (CBC/CTR, DIGESTS=NONE). Package presence is not proof of hardware
execution or a throughput improvement; this does not add AES-GCM or automatic
Go/Xray acceleration. Verify /dev/crypto and `openssl engine -t -c devcrypto`
on a separately authorized device installation.

The XG2010G-only uci-defaults script selects zh_cn when the saved LuCI language
is absent or auto. Explicit saved choices, including another language, survive.
DNS servers remain user configuration.

Argon 3.0.0-r20261019 includes its configuration UI and provides
luci-app-argon-config. The pinned LuCI Makefile declares this explicitly.
Do not restore the old standalone package; keep its Chinese translation.
Earlier audit descriptions equating its missing package name with a missing
configuration UI were incorrect.
