import copy
import fcntl
import ipaddress
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from ikb_addon_api import Api, ROOT, Transaction, atomic_json, body

STATE = ROOT / 'whatsapp-addon-state.json'
DOMAINS = ['whatsapp.com', 'whatsapp.net', 'wa.me']

def settings(cfg):
    return cfg.get('openwrt-addons', {}).get('whatsapp', {})

def source_data(api, anchor):
    names = [name.strip() for name in anchor.get('src-addr-opt-ipgroup', '').split(',') if name.strip()]
    objects, intervals = [], []
    groups = api.rows('route_object') if names else []
    for name in names:
        matches = [row for row in groups if row.get('type') == 0 and row.get('group_name') == name]
        if len(matches) != 1:
            raise ValueError('Source IP group must exist and have a unique name: ' + name)
        group = matches[0]
        objects.append({'type': 0, 'gid': group['group_id'], 'gp_name': name})
        intervals.extend(item['ip'] for item in group['group_value'])
    custom = [] if names else [value.strip() for value in anchor.get('src-addr', '').split(',') if value.strip()]
    intervals.extend(custom)
    ranges = []
    for value in intervals:
        if '-' in value:
            first, last = value.split('-', 1)
            ranges.append((int(ipaddress.IPv4Address(first)), int(ipaddress.IPv4Address(last))))
        else:
            network = ipaddress.ip_network(value, strict=False)
            if network.version != 4:
                raise ValueError('WhatsApp addon supports IPv4 source groups')
            ranges.append((int(network.network_address), int(network.broadcast_address)))
    return {'custom': custom, 'object': objects}, ranges, ', '.join(names or custom) or '全部终端'

def dhcp_matches(row, ranges):
    for key in ('addr_pool', 'ip_range', 'range', 'pool', 'ippool', 'ip_pool'):
        value = row.get(key)
        if isinstance(value, str) and '-' in value:
            try:
                first, last = value.split('-', 1)
                low, high = int(ipaddress.IPv4Address(first)), int(ipaddress.IPv4Address(last))
                return any(start <= low <= high <= end for start, end in ranges)
            except ValueError:
                pass
    gateway = ipaddress.IPv4Address(row['gateway'])
    mask = row.get('netmask') or row.get('net_mask')
    if not mask:
        raise ValueError('DHCP scope netmask unavailable; select DHCP scope IDs explicitly')
    network = ipaddress.ip_network(str(gateway) + '/' + str(mask), strict=False)
    return any(max(int(network.network_address) + 1, start) <= min(int(network.broadcast_address) - 1, end) for start, end in ranges)

def plan(api, cfg, options, state):
    tag = options.get('anchor-tag', 'gfw')
    anchors = [row for row in cfg.get('stream-domain', []) if row.get('tag') == tag]
    if len(anchors) != 1:
        raise ValueError('Choose a unique domain rule tag to follow: ' + tag)
    anchor = anchors[0]
    interface = anchor.get('interface', '')
    if not interface or not any(row.get('name') == interface for row in api.rows('wan')):
        raise ValueError('Configured WAN interface does not exist: ' + interface)
    source, ranges, label = source_data(api, anchor)
    rows = api.rows('stream_domain')
    owned = state.get('domain')
    candidates = [row for row in rows if set(row.get('domain', {}).get('custom', [])) == set(DOMAINS) and row.get('id') != (owned or {}).get('id')]
    if candidates and not owned:
        if not options.get('adopt-existing', False) or len(candidates) != 1:
            raise ValueError('Existing WhatsApp domain rule found; explicitly enable adoption after reviewing the preview')
    domain = {'enabled': 'yes', 'tagname': 'IKBWhatsApp', 'interface': interface, 'src_addr': source, 'domain': {'custom': DOMAINS, 'object': []}, 'comment': 'IkuaiBypassWA', 'time': {'custom': [{'type': 'weekly', 'weekdays': '1234567', 'start_time': '00:00', 'end_time': '23:59', 'comment': ''}], 'object': []}, 'prio': 31}
    line = None
    line_candidate = None
    if options.get('line-dns-enabled', False):
        address = options.get('line-dns', '')
        if not address:
            address = subprocess.check_output(['uci', '-q', 'get', 'network.lan.ipaddr'], text=True).strip().split('/')[0]
        ipaddress.IPv4Address(address)
        secondary = options.get('line-dns-backup', '8.8.8.8')
        ipaddress.IPv4Address(secondary)
        matches = [row for row in api.rows('dns_replace') if row.get('interface') == interface]
        if len(matches) > 1:
            raise ValueError('Multiple line DNS rules found for ' + interface)
        line_candidate = matches[0] if matches else None
        line = {'enabled': 'yes', 'tagname': (line_candidate or {}).get('tagname', 'IKBWADNS'), 'interface': interface, 'dns1': address, 'dns2': secondary, 'comment': (line_candidate or {}).get('comment', '')}
    dhcp = []
    if options.get('dhcp-enabled', False):
        if not ranges:
            raise ValueError('DHCP changes require an explicit source address range')
        first, second = options.get('client-dns1', '119.29.29.29'), options.get('client-dns2', '223.5.5.5')
        ipaddress.IPv4Address(first)
        ipaddress.IPv4Address(second)
        selected = [int(value.strip()) for value in options.get('dhcp-scope-ids', '').split(',') if value.strip()]
        for row in api.rows('dhcp_server'):
            if (row['id'] in selected) if selected else dhcp_matches(row, ranges):
                desired = dict(row, dns1=first, dns2=second)
                dhcp.append((row, desired))
        if not dhcp or (selected and set(selected) != {row['id'] for row, desired in dhcp}):
            raise ValueError('No matching DHCP scopes, or configured scope IDs no longer exist')
    return {'interface': interface, 'source_label': label, 'domain': domain, 'domain_candidate': candidates[0] if candidates and not owned else None, 'line': line, 'line_candidate': line_candidate, 'dhcp': dhcp}

def load_state():
    if STATE.is_symlink():
        raise ValueError('Addon state must not be a symbolic link')
    return json.loads(STATE.read_text()) if STATE.exists() else {}

def run(cfg, action):
    options = settings(cfg)
    enabled = options.get('enabled', False)
    state = load_state()
    if not enabled and not state:
        return {'ok': True, 'message': 'WhatsApp 附加功能未启用，没有修改爱快配置。'}
    api = Api(cfg)
    if action == 'whatsapp-diagnose':
        address = options.get('diagnostic-ip', '')
        ipaddress.IPv4Address(address)
        result = api.call('monitor_lanip', 'show', {'TYPE': 'conn,conn_num', 'ip': address, 'limit': '0,1000'}).get('results', {})
        rows = result.get('conn', [])
        relevant = [{key: row.get(key) for key in ['dst_addr', 'dst_port', 'interface', 'status', 'domain', 'total_up', 'total_down']} for row in rows if row.get('dst_port') in (443, 5222, 5223, 853)]
        dot = sum(row.get('dst_port') == 853 for row in rows)
        return {'ok': True, 'message': '终端 ' + address + '：检测到 ' + str(dot) + ' 条 DoT/853 连接。Android 请将私人 DNS 明确设为关闭，重连 Wi-Fi 后重试。\n' + json.dumps(relevant, ensure_ascii=False, indent=2)}
    main_dns = api.rows('dns', 'dns_config')
    target = plan(api, cfg, options, state) if enabled else None
    description = ('出口 ' + target['interface'] + '；源范围 ' + target['source_label'] + '；WhatsApp 域名 ' + ', '.join(DOMAINS) + '；多线路 DNS ' + ('同步' if target['line'] else '不修改') + '；DHCP 范围 ' + ', '.join(str(row['id']) + '/' + row.get('interface', '') for row, desired in target['dhcp'])) if target else '关闭附加功能，恢复接管前设置并删除由附加功能创建的规则。'
    if action == 'whatsapp-preview':
        return {'ok': True, 'message': '预览：' + description + '。爱快全局主备 DNS 不会修改。Android 私人 DNS 需在终端关闭。'}
    if action != 'whatsapp-sync':
        raise ValueError('Unsupported WhatsApp operation')
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / '.whatsapp-addon.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another WhatsApp addon operation is active')
        current_state = load_state()
        if current_state != state:
            raise ValueError('Addon state changed; retry the operation')
        old_state = copy.deepcopy(state)
        tx = Transaction(api, old_state)
        for record in [state.get('domain'), state.get('line')] + state.get('dhcp', []):
            if record:
                tx.check_owned(record)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        atomic_json(ROOT / 'backups' / ('whatsapp-addon-' + stamp + '.json'), {'state': state, 'main_dns': main_dns, 'plan': target})
        new_state = {}
        try:
            if enabled:
                new_state['domain'] = tx.apply('stream_domain', target['domain'], state.get('domain'), target['domain_candidate'])
                previous_line = state.get('line')
                same_line = previous_line and previous_line['after'].get('interface') == target['interface']
                if target['line']:
                    new_state['line'] = tx.apply('dns_replace', target['line'], previous_line if same_line else None, target['line_candidate'] if not same_line else None)
                existing = {record['id']: record for record in state.get('dhcp', [])}
                new_state['dhcp'] = [tx.apply('dhcp_server', desired, existing.get(row['id']), row if row['id'] not in existing else None) for row, desired in target['dhcp']]
                if previous_line and (not target['line'] or not same_line):
                    tx.restore(previous_line)
                wanted = {record['id'] for record in new_state['dhcp']}
                for record in state.get('dhcp', []):
                    if record['id'] not in wanted:
                        tx.restore(record)
            else:
                for record in [state.get('domain'), state.get('line')] + state.get('dhcp', []):
                    if record:
                        tx.restore(record)
            if api.rows('dns', 'dns_config') != main_dns:
                raise ValueError('Global DNS changed concurrently; addon transaction cancelled')
            atomic_json(STATE, new_state)
        except Exception:
            try:
                tx.rollback()
            finally:
                atomic_json(STATE, old_state)
            raise
    return {'ok': True, 'message': '已同步：' + description + '。爱快全局主备 DNS 保持不变。'}
