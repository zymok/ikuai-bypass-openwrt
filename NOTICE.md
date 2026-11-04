# 来源与版权声明

## 上游核心

- 原项目：[joyanhui/ikuai-bypass](https://github.com/joyanhui/ikuai-bypass)
- 原作者：[joyanhui](https://github.com/joyanhui)，以及原项目贡献者；上游 README 同时致谢 [ztc1997](https://github.com/ztc1997/ikuai-bypass/) 的初始思路。
- 本安装包使用版本：`ikuai-bypass-v4.4.110`，官方 Linux x86_64 CLI 发布文件。
- 本项目未修改该 Rust 核心二进制；新增功能在 OpenWrt 包装层实现。
- 上游许可证：GNU Affero General Public License v3.0，本仓库沿用，完整文本见 `LICENSE`。
- 对应核心源码和校验信息见 `vendor/UPSTREAM.json` 及上游源码归档，构建过程见 `docs/build.md`。

## 本项目修改

维护账号：[zymok](https://github.com/zymok)。修改内容为 Lua LuCI 控制器与表单、配置操作辅助程序、IPK 打包、procd 集成、WhatsApp 附加配置、订阅保护、测试及文档。修改日期见 `CHANGELOG.md`。

本仓库为非官方增强版，不是 joyanhui 的官方客户端分支或官方发布。保留原项目名称用于说明兼容性和来源，不表示原作者认可或承担本修改版的维护责任。

## 第三方依赖与规则

| 项目 | 版本/用途 | 许可/来源 |
| --- | --- | --- |
| PyYAML | 6.0.3，纯 Python YAML 解析 | MIT，`package/vendor/PyYAML-LICENSE`，https://pyyaml.org/ |
| ruamel.yaml | 0.18.16，YAML 往返编辑 | MIT，`package/vendor/ruamel-LICENSE`，https://pypi.org/project/ruamel.yaml/ |
| Loyalsoldier/v2ray-rules-dat | GFW 订阅链接 | https://github.com/Loyalsoldier/v2ray-rules-dat |
| Loyalsoldier/geoip | IP 订阅链接 | https://github.com/Loyalsoldier/geoip |

规则内容由各规则项目维护，本仓库主要预设其公开链接；对应许可及使用说明以各规则项目为准。
