# iKuai Bypass for OpenWrt

![OpenWrt](https://img.shields.io/badge/OpenWrt-LuCI-00a6d2) ![Architecture](https://img.shields.io/badge/arch-x86__64-blue) ![Package](https://img.shields.io/badge/IPK-4.4.110--13-brightgreen) ![License](https://img.shields.io/badge/license-AGPL--3.0-blue)

**在 OpenWrt 的 LuCI 界面中管理爱快分流规则、订阅链接和更新计划。** 集成上游核心、中文配置界面、WhatsApp 可选附加功能及订阅更新保护，提供可直接安装的 IPK。

> **原作者与项目来源：** 本项目基于 **[joyanhui/ikuai-bypass](https://github.com/joyanhui/ikuai-bypass)**，原作者为 **[joyanhui](https://github.com/joyanhui)**。核心程序使用上游 **ikuai-bypass-v4.4.110** 的官方 Linux x86_64 发布文件，未修改 Rust 核心。本仓库由 [zymok](https://github.com/zymok) 整理维护 OpenWrt 包装层、LuCI、附加功能与文档，属于**非官方增强版**，不代表原作者发布或背书。感谢原作者及上游所有贡献者。

## 下载与文档

| 入口 | 内容 |
| --- | --- |
| [下载最新版本](https://github.com/zymok/ikuai-bypass-openwrt/releases/latest) | IPK、SHA-256、源码归档 |
| [安装与升级](docs/install.md) | 兼容环境、安装、覆盖升级、卸载 |
| [配置与日常操作](docs/configuration.md) | 账号、规则链接、出口、源分组、运行模式、计划与日志 |
| [微信推送](docs/serverchan.md) | Server 酱 Turbo 设置、测试通知及更新详情 |
| [Telegram / ChatGPT 应用增强](docs/applications.md) | 自动跟随 WAN/源分组、Telegram IP、ChatGPT 域名、DNS 防泄漏 |
| [WhatsApp 附加功能](docs/whatsapp.md) | 跟随 WAN、线路 DNS、可选 DHCP、Android 注意事项 |
| [订阅更新保护](docs/subscription-guard.md) | 下载失败与空列表保护、适用范围和边界 |
| [常见问题](docs/faq.md) | 依赖、500 页面、DNS 与访问排查 |
| [源码构建](docs/build.md) | 固定上游版本、依赖来源、测试与打包 |
| [测试记录](docs/testing.md) | 本版测试场景与验证边界 |
| [版本记录](CHANGELOG.md) | 核心版本与安装包修订的区别 |
| [原作者完整文档](https://joyanhui.github.io/ikuai-bypass/) | 上游设计、配置及核心功能说明 |

## 主要功能

- **中文 LuCI 管理：** 表单编辑账号、代理、订阅、WAN、源地址组、下一跳、协议、运行模式与更新计划，也可编辑完整 YAML。
- **订阅预设：** GFW、MYBYPASS、MYDIRECT、国内 IP、Telegram、Google、IPv6 等；默认展示已保存链接，可自行修改或添加规则。
- **微信推送：** 可配置 Server 酱 Turbo、自定义路由名称和测试通知。失败通知附本轮错误日志摘录。
- **日常操作：** 登录测试、订阅连接测试、单次同步、启动/停止、开机启动、日志、按 tag 清理、域名导出、配置备份与恢复。
- **Telegram / ChatGPT 增强：** 可选自动生成完整应用规则，随计划更新；支持 DNS 入口防泄漏及 PassWall2 TCP 端口管理。
- **WhatsApp 附加功能：** 可选启用，出口和源地址组自动跟随指定域名规则；分别选择线路 DNS 和 DHCP 下发 DNS，不修改爱快全局主备 DNS。
- **订阅更新保护：** 下载并校验列表后才交给核心更新。下载失败、空列表、错误页、非法内容或明确的响应截断会被拒绝，保留对应旧规则；手动更新和定时服务均覆盖。
- **便于批量部署：** IPK 包含核心和 YAML 纯 Python 依赖；每台路由器自行填写账号、出口与源分组，安装包不包含现场密码。

## 支持环境

| 项目 | 当前支持范围 |
| --- | --- |
| OpenWrt | x86_64、使用 **opkg**，已在 OpenWrt/BleachWrt 24.10 系列环境验证 |
| LuCI | Lua CBI 页面，依赖 `luci-base`、`luci-compat` |
| 爱快 | 与上游 v4.4.110 一致，面向 **爱快 4.x**；3.7.x 请参考原作者兼容版本 |
| 系统依赖 | `python3`、`ca-bundle`，缺少时需要匹配的软件源 |
| 其他架构/包管理器 | 当前不提供 ARM、MIPS 或 apk 安装包，不保证直接兼容 |

这不是代理节点客户端。OpenWrt 的代理出口和 DNS 必须先正常工作，规则同步才能实现预期分流。

## 快速开始

从 [Releases](https://github.com/zymok/ikuai-bypass-openwrt/releases/latest) 下载 IPK，上传至 OpenWrt `/tmp/`，执行：

```sh
opkg update
opkg install /tmp/luci-app-ikuai-bypass_4.4.110-13_x86_64.ipk
```

进入 **LuCI → 服务 → iKuai Bypass**：

1. 填写爱快地址、账号、密码；自签名 HTTPS 按实际情况选择证书选项。
2. 核对示例规则及订阅链接，把 WAN 和源地址组改成自己的配置。
3. 保持定时服务停止，点击“立即更新一次”，确认日志和爱快规则更新成功。
4. 选择更新计划，保存，开启自启并启动服务。修改配置后重启服务。

首次安装默认不启动同步，爱快密码为空，应用增强默认关闭。不要未经核对直接启用示例规则。完整步骤见[安装说明](docs/install.md)。

## 版本与更新保护

当前安装包版本 **4.4.110-13**：`4.4.110` 是上游核心版本，末尾 `-13` 是本项目的 OpenWrt 安装包修订号，不表示上游发布了同名版本。

更新保护按订阅生效，并非爱快写入事务：一个订阅失败时保留它的旧规则，其他正常订阅仍可更新。**不保证爱快写入中途失败的完整回滚**，也不能识别所有语法正确但内容错误的非空列表。详见[保护说明及测试](docs/subscription-guard.md)。

## 源码、许可与反馈

本项目沿用 **AGPL-3.0**，许可证见 [LICENSE](LICENSE)，上游和第三方来源见 [NOTICE.md](NOTICE.md)。包装层源码位于 `package/`，构建入口为 `build.py`，测试位于 `tests/`。对应上游核心源码随版本以归档提供，并标明固定版本与校验值，详见[构建文档](docs/build.md)。

修改版问题请提交到[本仓库 Issues](https://github.com/zymok/ikuai-bypass-openwrt/issues)，附安装包版本、固件版本及已脱敏日志。不要上传密码、完整配置备份或私人网络信息。上游项目值得支持，欢迎访问 [joyanhui/ikuai-bypass](https://github.com/joyanhui/ikuai-bypass) 点 Star。
