# 安装、升级与卸载

## 安装前

确认架构是 `x86_64`，使用 `opkg`，且软件源与固件版本匹配：

```sh
uname -m
command -v opkg
cat /etc/openwrt_release
```

依赖为 `luci-base`、`luci-compat`、`python3`、`ca-bundle`。PyYAML 和 ruamel.yaml 的纯 Python 模块已包含在包内，不需要 `python3-yaml`。本项目只提供 x86_64 IPK，不是全依赖离线套件。

## 首次安装

从 [Releases](https://github.com/zymok/ikuai-bypass-openwrt/releases/latest) 下载 IPK 及对应 `.sha256`，上传到 `/tmp/`：

```sh
cd /tmp
sha256sum -c luci-app-ikuai-bypass_4.4.110-13_x86_64.ipk.sha256
opkg update
opkg install ./luci-app-ikuai-bypass_4.4.110-13_x86_64.ipk
```

刷新 LuCI，进入“服务 → iKuai Bypass”。未出现菜单时退出 LuCI 后重新登录。初始服务和自启关闭，密码为空，上游独立 WebUI 默认关闭。

如果之前装过原作者的同名 LuCI 包，应先下载旧配置备份、停止旧服务并检查原安装路径。此包不自动迁移 `/opt/ikuai-bypass/config.yml`，也不负责清理旧 `/opt` 安装。

## 覆盖升级

同系列安装包可以使用 `opkg install` 覆盖升级。升级前在 LuCI 下载配置备份；启用 WhatsApp 附加功能时，应同时私下备份整个 `/etc/ikuai-bypass/`，保留附加功能状态文件。

```sh
/etc/init.d/ikuai-bypass stop
opkg install /tmp/luci-app-ikuai-bypass_4.4.110-13_x86_64.ipk
```

`/etc/ikuai-bypass/config.yml` 是 conffile，正常升级保留原文件。出现 `.yml-opkg` 提示表示新默认配置另存，不要直接覆盖自己的配置。新增表单字段会显示默认值。

确认规则、账号和更新计划后重新启用服务。升级过程会停止服务并关闭自启，因此需要重新开启：

```sh
/etc/init.d/ikuai-bypass enable
/etc/init.d/ikuai-bypass start
```

## 配置保存与备份

配置路径 `/etc/ikuai-bypass/config.yml`，权限 0600。LuCI 支持下载备份，也可将备份原文粘贴进“完整 YAML”，选择对应保存方式后保存。配置包含爱快密码，必须作为私有文件保存。

修改配置后重启服务。恢复 WhatsApp 附加功能时还需对应的 `whatsapp-addon-state.json`；它记录创建/接管的规则及原值，不能随意删除。

## 卸载

```sh
/etc/init.d/ikuai-bypass stop
/etc/init.d/ikuai-bypass disable
opkg remove luci-app-ikuai-bypass
```

卸载 OpenWrt 软件不会自动删除爱快中已经同步的规则。需要删除时，先在软件仍安装时按明确 tag 执行清理；WhatsApp 附加规则应先关闭功能、保存并同步以恢复接管前状态。不要用空订阅清空规则。

## Telegram / ChatGPT 新功能

4.4.110-10 新增应用增强页，升级不会自动开启。按 [应用增强说明](applications.md) 选择跟随规则和所需开关，保存、预览、停止服务、立即同步，再启动定时服务。备份时保留应用网络状态文件；卸载前如需恢复端口或移除本机 DNS 保护，先关闭相应开关并同步。

从 4.4.110-13 起，失败通知附错误日志摘录。覆盖升级会保留已配置的 SendKey 与推送标题。首次启用见 [微信推送指南](serverchan.md)。
