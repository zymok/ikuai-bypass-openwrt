local fs = require 'nixio.fs'
local sys = require 'luci.sys'
local json = require 'luci.jsonc'
local nixio = require 'nixio'
local result = json.parse(sys.exec('/usr/libexec/ikuai-bypass-config read')) or {}
local form = SimpleForm('ikuai_bypass', 'iKuai Bypass', '在 OpenWrt 上同步爱快分流规则。保存后请重启服务。')
form.reset = false
if not result.ok then
    form.message = result.error or 'Failed to read configuration'
end
local section = form:section(SimpleSection)
section.template = 'cbi/nsection'
section.section = 1
section.cfgvalue = function() return true end
section:tab('basic', '基本设置')
section:tab('advanced', '代理与高级参数')
section:tab('runtime', '运行与日志')
section:tab('notifications', '微信推送', '使用 Server 酱 Turbo 已配置的微信通道。先保存 SendKey，再发送测试通知。保存后重启服务，让定时任务读取新设置。')
section:tab('applications', 'Telegram / ChatGPT', '默认关闭。先保存设置并预览，停止定时服务后立即同步，再启动服务。应用规则在运行时生成并随计划更新，不会覆盖普通规则表单或启用未选模块的示例规则。关闭应用开关不会自动删除已同步的爱快规则；可在运行与日志按 TGClient／ChatGPT 清理。')
section:tab('addons', 'WhatsApp 附加功能', '跟随域名规则的出口与源地址组。先保存设置，再预览或同步。Android 私人 DNS 请明确选择关闭；不自动修改终端设置。')
section:tab('yaml', '完整 YAML')
for _, group in ipairs((result.schema or {}).groups or {}) do section:tab(group.key, group.label, group.help) end
local status = section:taboption('basic', DummyValue, '_status', '运行状态')
status.cfgvalue = function()
    return (sys.call("pidof ikuai-bypass >/dev/null 2>&1") == 0 and '运行中' or '已停止') .. (sys.call('/etc/init.d/ikuai-bypass enabled') == 0 and '；开机启动已开启' or '；开机启动已关闭')
end
local service_action
for _, action in ipairs({'start', 'stop', 'restart', 'enable', 'disable'}) do
    local labels = {start='启动', stop='停止', restart='重启', enable='开启自启', disable='关闭自启'}
    local button = section:taboption('basic', Button, '_' .. action, labels[action])
    button.inputtitle = labels[action]
    button.write = function()
        service_action = action
    end
end
local kind = section:taboption('basic', ListValue, '_editor', '保存方式')
kind:value('fields', '保存各页表单（基本设置、高级参数、规则）')
kind:value('raw', '完整 YAML（含所有分流规则）')
kind.default = 'fields'
local options = {}
local schedules = {
    {'0 3 * * *', '每天凌晨 03:00（推荐）'},
    {'0 7 * * *', '每天早上 07:00'},
    {'0 0 * * *', '每天凌晨 00:00'},
    {'0 * * * *', '每小时整点'},
    {'0 */6 * * *', '每 6 小时（00、06、12、18 点）'},
    {'0 */12 * * *', '每 12 小时（00、12 点）'},
    {'0 3 * * SUN', '每周日凌晨 03:00'},
}
local schedule_values = {}
for _, schedule in ipairs(schedules) do schedule_values[schedule[1]] = true end
local choices = {
    ['run-mode'] = {
        {'cronAft', '仅按计划更新：启动后等待下次计划时间（推荐）'},
        {'cron', '立即更新并定时：每次启动先更新一次，再按计划更新'},
        {'once', '仅更新一次：每次启动更新一次，完成后退出'},
    },
    mode = {
        {'ispdomain', '运营商与域名分流：同步自定义运营商 IP 列表及域名分流规则'},
        {'ipgroup', 'IPv4 分组与端口分流：同步 IPv4 分组及线路／下一跳规则'},
        {'ipv6group', '仅 IPv6 分组：同步 IPv6 地址列表到爱快分组'},
        {'ii', 'IPv4 混合：运营商、域名分流、IPv4 分组及端口分流'},
        {'ip', '双栈分组：IPv4、IPv6 分组及端口分流'},
        {'iip', '完整混合：运营商、域名分流、IPv4／IPv6 分组及端口分流'},
    },
    ['ikuai-url-ignore-cert'] = {{'false', '校验证书'}, {'true', '忽略证书错误（适用于内网自签名证书）'}},
}
local labels = {['ikuai-url']='爱快管理地址', username='用户名', password='密码', cron='更新计划', ['run-mode']='运行模式', mode='分流模式', ['github-proxy']='GitHub 下载代理前缀', ['ikuai-url-ignore-cert']='爱快 HTTPS 证书验证'}
for _, key in ipairs({'ikuai-url', 'username', 'password', 'cron', 'run-mode', 'mode', 'github-proxy', 'ikuai-url-ignore-cert'}) do
    local option
    if key == 'cron' or choices[key] then
        option = section:taboption('basic', ListValue, key, labels[key])
        for _, choice in ipairs(key == 'cron' and schedules or choices[key]) do option:value(choice[1], choice[2]) end
        if key == 'cron' then
            option:value('custom', '自定义时间（Cron 表达式）')
            option.description = '按路由器本地时间执行，请在系统设置中确认时区。定时运行时生效；“仅更新一次”不使用更新计划。'
        elseif key == 'run-mode' then
            option.description = '仅按计划更新不会在启动时立即同步；立即更新并定时适合现在同步并持续更新；仅更新一次适合手动更新，完成后显示为已停止。'
        elseif key == 'mode' then
            option.description = '已有运营商／域名规则可选运营商与域名分流；通过旁路由 IP 作为下一跳可选 IPv4 分组与端口分流；需要多类规则同时同步时选择混合模式。下方可修改订阅链接；新增规则、线路及下一跳在完整 YAML 中配置。'
        end
    else
        option = section:taboption('basic', Value, key, labels[key])
    end
    option.password = key == 'password'
    option.rmempty = true
    option:depends('_editor', 'fields')
    option.cfgvalue = function()
        local submitted = option:formvalue('1')
        if submitted ~= nil then return submitted end
        local value = (result.fields or {})[key]
        if value == nil then return '' end
        if key == 'cron' and not schedule_values[tostring(value)] then return 'custom' end
        return tostring(value)
    end
    options[key] = option
end
local custom_cron = section:taboption('basic', Value, '_custom_cron', '自定义 Cron 表达式')
custom_cron:depends({_editor='fields', cron='custom'})
custom_cron.description = '通常依次填写：分钟、小时、日期、月份、星期。例如 30 2 * * * 表示每天 02:30；星期建议用 MON 至 SUN。也保留核心支持的 6／7 段扩展表达式。'
custom_cron.cfgvalue = function() return (result.fields or {}).cron or '' end
local raw = section:taboption('yaml', TextValue, '_raw', '配置原文（在基本设置中选择完整 YAML 保存方式后保存）')
raw.rows = 35
raw.cfgvalue = function() return raw:formvalue('1') or result.raw or '' end
local function make_option(tab, name, spec, current)
    local option = section:taboption(tab, (spec.choices or spec.type == 'bool') and ListValue or Value, name, spec.label, spec.help)
    if spec.type == 'bool' then
        option:value('false', '关闭')
        option:value('true', '开启')
    else
        for _, choice in ipairs(spec.choices or {}) do option:value(choice[1], choice[2]) end
    end
    option.rmempty = true
    option.password = spec.secret or false
    if spec.type == 'int' then option.datatype = 'integer' end
    option.cfgvalue = function()
        local submitted = option:formvalue('1')
        if submitted ~= nil then return submitted end
        if current == nil then current = spec.default end
        return tostring(current)
    end
    return option
end
local function value_of(option, spec)
    local value = option:formvalue('1')
    if value == nil then return nil end
    if spec.type == 'bool' then return value == 'true' end
    if spec.type == 'int' then return tonumber(value) end
    return value
end
local settings = {}
for _, spec in ipairs((result.schema or {}).settings or {}) do
    if spec.path == 'openwrt-addons.whatsapp.anchor-tag' or spec.path == 'openwrt-addons.applications.anchor-tag' then
        spec.choices = {}
        for _, rule in ipairs((result.rules or {})['stream-domain'] or {}) do
            spec.choices[#spec.choices + 1] = {rule.tag, rule.tag .. '（出口 ' .. (rule.interface or '') .. '）'}
        end
        if #spec.choices == 0 then spec.choices = nil end
    end
    local option = make_option(spec.tab or 'advanced', '_setting_' .. spec.path:gsub('%.', '_'), spec, (result.values or {})[spec.path])
    settings[#settings + 1] = {spec=spec, option=option}
end
local rule_forms = {}
local new_forms = {}
for _, group in ipairs((result.schema or {}).groups or {}) do
    for index, rule in ipairs((result.rules or {})[group.key] or {}) do
        local prefix = '_rule_' .. group.key .. '_' .. tostring(index)
        local title = section:taboption(group.key, DummyValue, prefix .. '_title', '规则 ' .. tostring(index))
        title.cfgvalue = function() return rule.tag or rule['opt-tagname'] or group.label end
        local row = {group=group.key, index=index - 1, fields={}}
        for _, spec in ipairs(group.fields) do
            local option = make_option(group.key, prefix .. '_' .. spec.key, spec, rule[spec.key])
            row.fields[#row.fields + 1] = {spec=spec, option=option}
        end
        row.remove = section:taboption(group.key, Flag, prefix .. '_remove', '删除这条规则（保存时执行）')
        row.remove.default = '0'
        rule_forms[#rule_forms + 1] = row
    end
    local prefix = '_new_' .. group.key
    local add = section:taboption(group.key, Flag, prefix, '新增一条规则（填好后勾选并保存）')
    add.default = '0'
    local row = {group=group.key, add=add, fields={}}
    for _, spec in ipairs(group.fields) do
        local option = make_option(group.key, prefix .. '_' .. spec.key, spec, spec.default)
        option:depends(prefix, '1')
        row.fields[#row.fields + 1] = {spec=spec, option=option}
    end
    new_forms[#new_forms + 1] = row
end
local preset = section:taboption('basic', ListValue, '_preset', '添加内置订阅预设（保存时执行）')
preset:value('', '不添加；保留当前规则')
for _, entry in ipairs((result.schema or {}).presets or {}) do preset:value(entry.id, entry.label) end
preset.description = '预设中的 wan1、wan2 是示例，请在对应规则页面改成实际网口。已存在的相同标识和链接不会重复添加。'
local remote_url = section:taboption('yaml', Value, '_remote_url', '远程完整 YAML 配置链接')
remote_url.description = '填写 HTTP／HTTPS 原始文件链接；载入后先预览，保存才会替换当前配置。'
local remote_button = section:taboption('yaml', Button, '_op_fetch', '载入远程配置到编辑框')
remote_button.inputtitle = '载入并预览'
remote_button.write = function() return true end
local operations = {}
for _, entry in ipairs({{'login', '测试爱快登录'}, {'proxy', '测试规则下载代理'}, {'once', '立即更新一次'}, {'export', '导出域名列表'}, {'cancel', '停止后台单次任务'}, {'whatsapp-preview', '预览 WhatsApp 同步范围'}, {'whatsapp-sync', '同步 WhatsApp 配置'}, {'whatsapp-diagnose', '诊断 WhatsApp 终端连接'}, {'apps-preview', '预览应用增强计划'}, {'apps-sync', '立即同步（含应用规则）'}, {'apps-diagnose', '诊断 Telegram / ChatGPT 连接'}}) do
    local button = section:taboption(entry[1]:match('^apps%-') and 'applications' or entry[1]:match('^whatsapp%-') and 'addons' or 'runtime', Button, '_op_' .. entry[1], entry[2])
    button.inputtitle = entry[2]
    button.write = function() return true end
    operations[entry[1]] = button
end
local clean_tag = section:taboption('runtime', Value, '_clean_tag', '要清理的规则标识')
local test_push = section:taboption('notifications', Button, '_op_serverchan-test', '发送测试通知')
test_push.inputtitle = '发送测试通知'
test_push.write = function() return true end
operations['serverchan-test'] = test_push
clean_tag.description = '填写要清理的 tag；填写 cleanAll 表示清理本工具管理的全部规则。'
local clean_confirm = section:taboption('runtime', Flag, '_clean_confirm', '确认从爱快删除指定规则')
local clean_button = section:taboption('runtime', Button, '_op_clean', '执行清理')
clean_button.inputtitle = '清理指定规则'
clean_button.write = function() return true end
operations.clean = clean_button
local export_link = section:taboption('runtime', DummyValue, '_export_link', '导出结果')
export_link.rawhtml = true
export_link.cfgvalue = function()
    if not fs.access('/tmp/ikuai-bypass-domains.tar.gz') then return '导出完成后在此下载；刷新页面查看。' end
    return '<a class="btn" href="' .. require('luci.dispatcher').build_url('admin', 'services', 'ikuai-bypass', 'export') .. '">下载域名列表压缩包</a>'
end
local logs = section:taboption('runtime', TextValue, '_logs', '最近任务和服务日志（刷新页面更新）')
logs.rows = 18
logs.readonly = true
logs.cfgvalue = function() return sys.exec('/usr/libexec/ikuai-bypass-operations logs') end
local backups = section:taboption('yaml', DummyValue, '_backup', '配置备份与恢复')
backups.rawhtml = true
backups.cfgvalue = function()
    return '<a class="btn" href="' .. require('luci.dispatcher').build_url('admin', 'services', 'ikuai-bypass', 'backup') .. '">下载当前配置备份</a><p>恢复时将备份原文粘贴到上方，选择完整 YAML 保存方式后保存。</p>'
end
function form.handle(self, state, data)
    if service_action then
        local code = sys.call('/etc/init.d/ikuai-bypass ' .. service_action .. ' >/dev/null 2>&1')
        self.message = code == 0 and '服务操作已执行；使用的是已保存的配置。' or '服务操作失败，请检查是否有后台任务或查看日志。'
        service_action = nil
        return true
    end
    if state ~= FORM_VALID or not result.ok then return true end
    if remote_button:formvalue('1') then
        local url = remote_url:formvalue('1') or ''
        local reply = json.parse(sys.exec('/usr/libexec/ikuai-bypass-operations fetch ' .. "'" .. url:gsub("'", "'\\''") .. "'")) or {}
        if reply.ok then
            raw.cfgvalue = function() return reply.raw end
            kind.cfgvalue = function() return 'raw' end
            self.message = '远程配置已载入编辑框；请核对内容并保存。此时还没有修改路由器配置。'
        else
            self.message = reply.error or 'Fetch failed'
        end
        return true
    end
    for action, button in pairs(operations) do
        if button:formvalue('1') then
            local tag = clean_tag:formvalue('1') or ''
            if action == 'clean' and (tag == '' or clean_confirm:formvalue('1') ~= '1') then
                self.message = '请填写规则标识并勾选清理确认。'
                return true
            end
            local command = '/usr/libexec/ikuai-bypass-operations ' .. action
            if action == 'clean' then command = command .. ' ' .. "'" .. tag:gsub("'", "'\\''") .. "'" end
            local reply = json.parse(sys.exec(command)) or {}
            self.message = require('luci.util').pcdata(reply.ok and (reply.message or '操作已完成。') or reply.error or 'Operation failed')
            return true
        end
    end
    local request = {kind=kind:formvalue('1') or 'fields', original=result.raw, fields={}, values={}, rules={}, additions={}}
    if request.kind == 'raw' then
        request.raw = raw:formvalue('1') or ''
    else
        for key, option in pairs(options) do
            local value = option:formvalue('1')
            if value ~= nil then
                request.fields[key] = key == 'ikuai-url-ignore-cert' and value == 'true' or value
                if key == 'ikuai-url-ignore-cert' then request.fields[key] = value == 'true' end
            end
        end
        if request.fields.cron == 'custom' then
            local expression = custom_cron:formvalue('1') or ''
            local count = 0
            for field in expression:gmatch('%S+') do count = count + 1 end
            if count < 5 or count > 7 then
                self.message = '自定义更新计划需填写 5 段 Cron，或核心支持的 6／7 段扩展表达式。'
                return true
            end
            request.fields.cron = expression
        end
        for _, entry in ipairs(settings) do request.values[entry.spec.path] = value_of(entry.option, entry.spec) end
        for _, row in ipairs(rule_forms) do
            local item = {group=row.group, index=row.index, fields={}, remove=row.remove:formvalue('1') == '1'}
            for _, entry in ipairs(row.fields) do item.fields[entry.spec.key] = value_of(entry.option, entry.spec) end
            request.rules[#request.rules + 1] = item
        end
        for _, row in ipairs(new_forms) do
            if row.add:formvalue('1') == '1' then
                local item = {group=row.group, fields={}}
                for _, entry in ipairs(row.fields) do item.fields[entry.spec.key] = value_of(entry.option, entry.spec) end
                request.additions[#request.additions + 1] = item
            end
        end
        for _, entry in ipairs((result.schema or {}).presets or {}) do
            if preset:formvalue('1') == entry.id then request.additions[#request.additions + 1] = {group=entry.group, fields=entry.fields} end
        end
    end
    local path = '/tmp/ikuai-bypass-config-' .. tostring(nixio.getpid())
    local handle = nixio.open(path, 'w', '600')
    if not handle then self.message = 'Failed to create private request file'; return true end
    handle:writeall(json.stringify(request))
    handle:close()
    local saved = json.parse(sys.exec('/usr/libexec/ikuai-bypass-config save < ' .. path)) or {}
    fs.remove(path)
    if saved.ok then
        require('luci.http').redirect(require('luci.dispatcher').build_url('admin', 'services', 'ikuai-bypass'))
        return false
    end
    self.message = saved.error or 'Save failed'
    return true
end
return form
