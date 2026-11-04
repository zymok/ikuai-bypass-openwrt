# OpenWrt LuCI 增强版 4.4.110-9

基于原作者 **[joyanhui/ikuai-bypass](https://github.com/joyanhui/ikuai-bypass)**，感谢 joyanhui 及上游贡献者。本发布为 zymok 整理的非官方 OpenWrt 包装增强版，核心固定为官方 v4.4.110，未修改 Rust 核心。

## 本版内容

- 中文 LuCI 规则、订阅链接、更新计划与服务管理。
- WhatsApp 可选附加功能：出口/源分组跟随，线路 DNS、DHCP DNS 分别控制。
- 订阅下载与有效列表保护：空列表、错误页、下载失败或非法内容保留旧规则。
- 单次/定时故障模拟测试、原作者标注、源码与构建/操作文档。

## 下载选择

- `luci-app-ikuai-bypass_4.4.110-9_x86_64.ipk`：OpenWrt x86_64 + opkg 安装包。
- 同名 `.ipk.sha256`：安装包校验值。
- `ikuai-bypass-openwrt-4.4.110-9-source.zip`：本项目源码，包含对应固定版本上游源码归档及第三方许可证。

依赖 `luci-base`、`luci-compat`、`python3`、`ca-bundle`；不依赖 `python3-yaml`。不提供 ARM/MIPS/apk 版本。

同系列可覆盖升级，保留原配置；升级后重新开启自启并启动服务。首次安装需自行填写爱快账号、出口和源分组。安装包不包含现场密码。完整说明见仓库 README 和 docs。

更新保护不是爱快写入事务，不保证写入中途失败自动回滚。Android 私人 DNS 需明确关闭；WhatsApp 通话仍需终端实际验证。

AGPL-3.0；原项目与第三方来源见仓库 `NOTICE.md`。修改版问题请在本仓库反馈。
