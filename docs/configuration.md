# 配置与日常操作

## 网络关系

典型结构是：内网终端 → 爱快 → 指定 WAN → OpenWrt 代理出口。OpenWrt 的 LAN 地址和爱快该 WAN 的网关位于同一网段。OpenWrt 自己的上联网口地址应避免再次命中返回自身的分流规则。

例如，OpenWrt LAN 是 `192.168.88.1/24`，爱快接入 WAN2，便在规则中填写 `wan2`。这里的地址仅为通用示例，按实际拓扑修改，不是安装后的自动网络设置。

## 基本设置

- **爱快地址、用户名、密码：** 填写自己路由器的管理信息。HTTPS 自签名可选择忽略证书错误，只用于自己信任的内网设备。
- **运行模式：** `cronAft` 等待下次计划时间；`cron` 启动先更新一次再定时；`once` 执行一次后退出。
- **分流模式：** 仅域名/运营商规则可选 `ispdomain`；IPv4 分组与端口分流选 `ipgroup`；IPv6 分组选 `ipv6group`；需要组合时选择界面中的混合模式。
- **更新计划：** 可选每天、每小时、每 6/12 小时、每周及自定义 Cron，按路由器本地时间执行。
- **规则下载代理：** 选择系统、智能 GitHub 前缀或自定义 HTTP/HTTPS 代理。先确认代理和 DNS 工作，再执行规则同步。

首次建议使用 `cronAft`，先手动更新，确认正常后再启动定时服务。

## 规则与链接

各类规则页展示当前配置中的链接，直接修改即可。可以新增/删除条目或使用内置预设。修改后保存，并重启服务。

| 常用预设 | 来源 |
| --- | --- |
| GFW | [Loyalsoldier/v2ray-rules-dat 的 gfw.txt](https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/release/gfw.txt) |
| MYBYPASS | [原作者 bypass-domain-list.txt](https://raw.githubusercontent.com/joyanhui/ikuai-bypass/main/private/bypass-domain-list.txt) |
| MYDIRECT | [原作者 direct-domain-list.txt](https://raw.githubusercontent.com/joyanhui/ikuai-bypass/main/private/direct-domain-list.txt) |
| 国内 IP / IPv6 | [Loyalsoldier/geoip 的 cn.txt](https://raw.githubusercontent.com/Loyalsoldier/geoip/release/text/cn.txt)，按目标地址类型筛选 |
| Telegram | [telegram.txt](https://raw.githubusercontent.com/Loyalsoldier/geoip/release/text/telegram.txt) |
| Google | [google.txt](https://raw.githubusercontent.com/Loyalsoldier/geoip/release/text/google.txt) |

规则链接由对应作者维护，内容和可用性由外部来源决定。IPv6 订阅若没有 IPv6 有效条目，保护层会拒绝更新并保留旧分组。

域名分流填写：

1. **tag：** 本工具管理规则的标识，保持简短且唯一，上游会添加 `IKB` 前缀及分片序号。
2. **出口：** 爱快实际 WAN 名称，例如 `wan2`，不是 Linux 物理网卡名。
3. **源地址：** 指定内网范围，或引用爱快中已创建的源 IP 分组。填写源 IP 分组时优先使用分组。
4. **订阅：** HTTP/HTTPS 原始纯文本链接；不要填写 GitHub 的网页 `blob` 地址。

MYDIRECT 等直连规则应填写直连 WAN，GFW/MYBYPASS 填代理出口 WAN。其他 IP 分组、IPv6 分组、自定义运营商、端口及下一跳设置依照上游配置含义填写，页面提供中文说明。

从配置中移除条目，不等于删除已同步到爱快的规则；需要在“运行与日志”中明确填写 tag 并执行清理。

## 单次更新与定时

1. 先停止定时服务，避免和单次任务重叠。
2. 点击“立即更新一次”，后台执行，刷新查看日志。
3. 检查 `GUARD:ACCEPT`、有效条目数量及更新成功信息；`GUARD:REJECT` 表示保护层拒绝该列表，旧规则保留。
4. 在爱快核对出口、源分组及规则数量，再启用自启并启动服务。

定时更新使用同一保护层。保护按订阅生效，不会因为一个订阅失败而删除它的旧规则，也不阻止其他订阅正常更新。

## DNS 和 WhatsApp

本程序同步规则，不会自动修复所有 DNS 链路。终端是否通过可识别的 DNS 查询、浏览器安全 DNS、Android 私人 DNS、代理出口是否通畅，都可能影响域名分流。

不要为了分流把整个网络的全局主 DNS 盲目改成 OpenWrt。需要线路 DNS 或 DHCP 下发设置时，使用可选的 [WhatsApp 附加功能](whatsapp.md)，先预览，再同步。Android 私人 DNS 需明确关闭，不能仅确认没有手动填写服务器。

## 批量部署

分发同一个 IPK，每台单独填写爱快地址/账号、WAN、源分组与 DHCP 范围。首次安装的模板不包含现场密码。不要把已配置机器的完整 YAML 公开放进仓库；也不要把一台路由器的附加功能状态文件直接用于另一台爱快。
