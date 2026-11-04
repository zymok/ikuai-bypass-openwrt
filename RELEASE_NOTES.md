# OpenWrt LuCI 增强版 4.4.110-10

基于原作者 **[joyanhui/ikuai-bypass](https://github.com/joyanhui/ikuai-bypass)**，感谢 joyanhui 及上游贡献者。本发布为 zymok 整理的非官方 OpenWrt 包装增强版，核心固定为官方 v4.4.110，未修改 Rust 核心。

## 本版新增

- LuCI **Telegram / ChatGPT** 应用增强页，各项默认关闭，升级不会擅自启用。
- Telegram IPv4 分组和端口分流、ChatGPT 依赖域名自动生成，WAN 和源范围跟随所选域名规则，并随更新计划维护。
- DNS 入口防泄漏：将已进入 OpenWrt 所选区域的 TCP/UDP 53 转到本机 LAN DNS 服务；不修改爱快全局主备 DNS 或 DHCP DNS。
- 可选管理已启用的 PassWall2 全 TCP 端口，关闭后恢复接管前列表。
- 预览、单次同步、终端连接诊断；同名接管、健康检查、失败回滚和外部改动拒绝。
- 按需组合有效模式，不启用基础模式中未选的示例规则；延续空列表与下载失败保护。

## 使用与升级

从附件下载 x86_64 IPK 及同名 SHA-256 校验文件。依赖 `luci-base`、`luci-compat`、`python3`、`ca-bundle`，不依赖 `python3-yaml`。本包不适用于 ARM/MIPS/apk 固件。

同系列可覆盖升级并保留配置。升级后打开“服务 → iKuai Bypass → Telegram / ChatGPT”，选择跟随规则和所需开关，保存并预览；停止定时服务后立即同步，确认成功再启动并开启自启。

关闭 Telegram/ChatGPT 会停止生成和更新，不自动删除已同步爱快规则；需要时按 TGClient/ChatGPT 显式清理。关闭 DNS 保护会移除本功能管理的入口规则，关闭 TCP 管理会恢复原列表。备份时保留整个私有配置目录及状态文件。

## 测试与边界

已覆盖应用开关、WAN/源范围跟随、重复同步、闲置示例不激活、空订阅保留旧规则、本机 DNS 与端口管理及失败回滚测试，并使用实际核心进行本机模拟接口测试。现场手机已验证 Telegram 和 ChatGPT 正常收发，尚不代表所有节点、IPv6 或语音视频通话都已验证。

保护不是爱快写入事务，不保证写入中途失败完整回滚。DNS 入口保护针对 IPv4 普通 53 端口，不覆盖终端自带 DoH/DoT。安装包及公开源码不含现场密码或私人配置。

附件包括 IPK、校验文件及完整源码 ZIP（含对应上游源码归档）。操作详见 [应用增强](https://github.com/zymok/ikuai-bypass-openwrt/blob/main/docs/applications.md)、[安装升级](https://github.com/zymok/ikuai-bypass-openwrt/blob/main/docs/install.md)。AGPL-3.0，来源见 NOTICE。
