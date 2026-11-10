# OpenWrt LuCI 增强版 4.4.110-13

本版加入 Server 酱 Turbo 微信推送。手动和定时更新结束后，通知会显示成功或失败、完成时间、订阅统计及有效条目数。失败通知附上本轮错误日志摘录，按类别合并并显示次数。摘录使用固定诊断文本，详细上下文请在 LuCI 的运行日志查看。

可设置路由名称区分设备。例如「家里路由 · ikuaibypass 规则更新成功」。升级后在 **服务 → iKuai Bypass → 微信推送** 填写 SendKey、开启推送并保存，然后发送测试通知和重启服务。新增开关默认关闭，已配置的用户可覆盖升级。

已验证手动和定时更新的成功、空订阅和爱快写入失败场景，以及真实微信测试通知和失败日志展示。

附件提供 x86_64 OpenWrt IPK、SHA-256 校验文件及对应源码。使用 opkg 安装，覆盖升级前请私下备份配置。配置、备份及 SendKey 请保存在自己的设备上。[安装与升级](https://github.com/zymok/ikuai-bypass-openwrt/blob/main/docs/install.md) · [微信推送指南](https://github.com/zymok/ikuai-bypass-openwrt/blob/main/docs/serverchan.md)

原作者 **joyanhui**。本项目是非官方 OpenWrt 包装增强版，核心仍使用上游官方 v4.4.110。许可为 AGPL-3.0，来源与第三方许可见 NOTICE。[上游项目](https://github.com/joyanhui/ikuai-bypass)
