import copy
import ipaddress
import json
import re
import secrets
import shlex
import socket
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ikb_addon_api import Api, atomic_json

ROOT = Path('/etc/ikuai-bypass')
TG_URL = 'https://core.telegram.org/resources/cidr.txt'
AI_URL = 'https://raw.githubusercontent.com/zymok/ikuai-bypass-openwrt/main/rules/chatgpt-domain-list.txt'
SECTION = 'firewall.ikb_dns_guard'
RULE_NAME = 'IKB-LAN-DNS-Guard'
GROUPS = ('custom-isp', 'stream-domain', 'ip-group', 'stream-ipport', 'ipv6-group')
ACTIVE = {
    'ispdomain': {'custom-isp', 'stream-domain'},
    'ipgroup': {'ip-group', 'stream-ipport'},
    'ipv6group': {'ipv6-group'},
    'ii': {'custom-isp', 'stream-domain', 'ip-group', 'stream-ipport'},
    'ip': {'ip-group', 'stream-ipport', 'ipv6-group'},
    'iip': set(GROUPS),
}


def settings(cfg):
    return cfg.get('openwrt-addons', {}).get('applications', {})


def anchor_rule(cfg):
    tag = settings(cfg).get('anchor-tag', 'gfw')
    matches = [r for r in cfg.get('stream-domain', []) if r.get('tag') == tag]
    if len(matches) != 1 or not matches[0].get('interface', '').strip():
        raise ValueError('Choose a unique domain rule with a WAN interface: ' + tag)
    return matches[0]


def checked_url(value):
    if not isinstance(value, str) or not value.startswith(('https://', 'http://')) or any(c.isspace() for c in value):
        raise ValueError('Application subscription requires an HTTP/HTTPS raw URL')
    return value


def prepare(cfg):
    opts = settings(cfg)
    tg, ai = opts.get('telegram-enabled', False), opts.get('chatgpt-enabled', False)
    result = copy.deepcopy(cfg)
    if not tg and not ai:
        return result
    anchor = anchor_rule(cfg)
    mode = cfg.get('mode', 'ispdomain')
    if mode not in ACTIVE:
        raise ValueError('Unsupported base mode')
    for group in GROUPS:
        if group not in ACTIVE[mode]:
            result[group] = []
    reserved = [('ip-group', 'tag', 'TGClient'), ('stream-ipport', 'opt-tagname', 'TGClient')] if tg else []
    if ai:
        reserved.append(('stream-domain', 'tag', 'ChatGPT'))
    for group, key, tag in reserved:
        if any(row.get(key) == tag for row in cfg.get(group, [])) and not opts.get('adopt-existing', False):
            raise ValueError('Reserved application tag already configured: ' + tag + '; review and enable adoption')
        result[group] = [row for row in result.get(group, []) if row.get(key) != tag]
    if tg:
        result.setdefault('ip-group', []).append({'tag': 'TGClient', 'url': checked_url(opts.get('telegram-url', TG_URL))})
        result.setdefault('stream-ipport', []).append({
            'opt-tagname': 'TGClient', 'type': '0', 'interface': anchor['interface'],
            'nexthop': '', 'src-addr': anchor.get('src-addr', ''),
            'src-addr-opt-ipgroup': anchor.get('src-addr-opt-ipgroup', ''),
            'src-addr-inv': 0, 'ip-group': 'TGClient', 'dst-addr-inv': 0,
            'prio': 31, 'mode': 1, 'ifaceband': 1, 'protocol': 'any',
        })
    if ai:
        result.setdefault('stream-domain', []).append({
            'tag': 'ChatGPT', 'url': checked_url(opts.get('chatgpt-url', AI_URL)),
            'interface': anchor['interface'], 'src-addr': anchor.get('src-addr', ''),
            'src-addr-opt-ipgroup': anchor.get('src-addr-opt-ipgroup', ''),
        })
    isp = bool(ACTIVE[mode] & {'custom-isp', 'stream-domain'}) or ai
    ip = bool(ACTIVE[mode] & {'ip-group', 'stream-ipport'}) or tg
    v6 = 'ipv6-group' in ACTIVE[mode]
    result['mode'] = ('iip' if isp and v6 else 'ii' if isp and ip else 'ispdomain' if isp else 'ip' if ip and v6 else 'ipgroup' if ip else 'ipv6group')
    return result


class Firewall:
    def zone_exists(self, zone):
        values = {}
        for line in subprocess.check_output(['uci', 'show', 'firewall'], text=True).splitlines():
            key, sep, value = line.partition('=')
            if sep:
                values[key] = value
        return any(value == 'zone' and shlex.split(values.get(key + '.name', '')) == [zone] for key, value in values.items())

    def read(self):
        command = subprocess.run(['uci', '-q', 'show', SECTION], capture_output=True, text=True)
        if command.returncode:
            return None
        result = {}
        for line in command.stdout.splitlines():
            left, sep, right = line.partition('=')
            if not sep:
                raise ValueError('Cannot parse firewall section')
            key = '__type' if left == SECTION else left[len(SECTION) + 1:]
            values = shlex.split(right)
            if len(values) != 1:
                raise ValueError('Unsupported list in managed firewall section')
            result[key] = values[0]
        return result

    def lan(self):
        value = subprocess.check_output(['uci', '-q', 'get', 'network.lan.ipaddr'], text=True).strip().split('/')[0]
        return str(ipaddress.IPv4Address(value))

    def write(self, values):
        subprocess.run(['uci', '-q', 'delete', SECTION], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if values is not None:
            subprocess.run(['uci', 'set', SECTION + '=' + values['__type']], check=True)
            for key, value in values.items():
                if key != '__type':
                    subprocess.run(['uci', 'set', SECTION + '.' + key + '=' + value], check=True)
        subprocess.run(['uci', 'commit', 'firewall'], check=True)

    def reload(self):
        result = subprocess.run(['/etc/init.d/firewall', 'reload'], capture_output=True, text=True, timeout=25)
        if result.returncode:
            raise ValueError('Firewall reload failed')

    def check_dns(self, address, port):
        identity = secrets.randbelow(65536)
        name = b''.join(bytes([len(p)]) + p.encode() for p in 'example.com'.split('.')) + b'\0'
        packet = struct.pack('!HHHHHH', identity, 0x100, 1, 0, 0, 0) + name + struct.pack('!HH', 1, 1)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(5)
            sock.connect((address, port))
            sock.send(packet)
            data = sock.recv(65535)
        if len(data) < 12:
            raise ValueError('Local DNS returned an incomplete response')
        reply_id, flags, questions, answers, _, _ = struct.unpack('!HHHHHH', data[:12])
        if reply_id != identity or not flags & 0x8000 or flags & 0xF or not answers:
            raise ValueError('Local DNS health check failed; firewall unchanged')


def dns_target(cfg, firewall):
    opts = settings(cfg)
    port = opts.get('dns-port', 53)
    zone = opts.get('dns-zone', 'lan')
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError('DNS port must be between 1 and 65535')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', zone):
        raise ValueError('Invalid ingress firewall zone')
    if not firewall.zone_exists(zone):
        raise ValueError('Ingress firewall zone does not exist: ' + zone)
    return {'__type': 'redirect', 'name': RULE_NAME, 'src': zone,
            'src_dport': '53', 'dest_ip': firewall.lan(), 'dest_port': str(port),
            'proto': 'tcp udp', 'target': 'DNAT', 'family': 'ipv4',
            'reflection': '0', 'enabled': '1'}


def sync_dns(cfg, firewall=None, state_path=None):
    import fcntl
    firewall = firewall or Firewall()
    state_path = state_path or ROOT / 'applications-dns-state.json'
    opts = settings(cfg)
    enabled = opts.get('dns-enabled', False)
    if not enabled and not state_path.exists():
        return 'DNS ingress protection inactive'
    state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state_path.parent / '.applications-dns.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if state_path.is_symlink():
            raise ValueError('DNS state must not be a symbolic link')
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        current = firewall.read()
        if state and current != state['after']:
            raise ValueError('DNS firewall rule changed outside the addon; refusing to overwrite it')
        if enabled and current is not None and not state:
            if current.get('name') != RULE_NAME or not opts.get('adopt-existing', False):
                raise ValueError('Existing DNS rule requires explicit adoption, or belongs to another application')
        desired = dns_target(cfg, firewall) if enabled else None
        if not enabled and not state:
            return 'DNS ingress protection inactive'
        if desired != current:
            if enabled:
                firewall.check_dns(desired['dest_ip'], int(desired['dest_port']))
            backup = state_path.parent / 'backups' / ('applications-dns-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
            atomic_json(backup, {'before': current, 'after': desired})
            try:
                firewall.write(desired)
                firewall.reload()
                atomic_json(state_path, {'after': desired} if enabled else {})
            except Exception:
                firewall.write(current)
                firewall.reload()
                raise
        else:
            atomic_json(state_path, {'after': desired} if enabled else {})
        return 'DNS ingress protection ' + ('enabled' if enabled else 'disabled')


def preview(cfg, firewall=None):
    opts = settings(cfg)
    staged = prepare(cfg)
    lines = ['Telegram：' + ('开启' if opts.get('telegram-enabled') else '关闭'),
             'ChatGPT：' + ('开启' if opts.get('chatgpt-enabled') else '关闭'),
             'DNS 入口保护：' + ('开启' if opts.get('dns-enabled') else '关闭'),
             'PassWall2 全 TCP 端口：' + ('开启' if opts.get('passwall2-tcp-all') else '不管理'),
             '基础模式 ' + cfg.get('mode', 'ispdomain') + ' → 有效模式 ' + staged.get('mode', 'ispdomain')]
    if opts.get('telegram-enabled') or opts.get('chatgpt-enabled'):
        anchor = anchor_rule(cfg)
        lines += ['出口：' + anchor['interface'], '源范围：' + (anchor.get('src-addr-opt-ipgroup') or anchor.get('src-addr') or '全部终端')]
    if opts.get('dns-enabled'):
        target = dns_target(cfg, firewall or Firewall())
        lines += ['DNS：来自 ' + target['src'] + ' 的 TCP/UDP 53 → ' + target['dest_ip'] + ':' + target['dest_port']]
    lines += ['预览不写入配置。爱快全局主备 DNS 和 DHCP 下发地址不修改。',
              '关闭应用开关会停止生成/更新对应规则；已同步的爱快规则需按 TGClient 或 ChatGPT 显式清理。']
    return '\n'.join(lines)


class ProxyPorts:
    key = 'passwall2.@global_forwarding[0].tcp_redir_ports'

    def read(self):
        return subprocess.check_output(['uci', '-q', 'get', self.key], text=True).strip()

    def enabled(self):
        return subprocess.run(['uci', '-q', 'get', 'passwall2.@global[0].enabled'], capture_output=True, text=True).stdout.strip() == '1'

    def write(self, value):
        subprocess.run(['uci', 'set', self.key + '=' + value], check=True)
        subprocess.run(['uci', 'commit', 'passwall2'], check=True)

    def restart(self):
        result = subprocess.run(['/etc/init.d/passwall2', 'restart'], capture_output=True, text=True, timeout=55)
        if result.returncode:
            raise ValueError('PassWall2 restart failed')


def sync_proxy_ports(cfg, backend=None, state_path=None):
    import fcntl
    backend = backend or ProxyPorts()
    state_path = state_path or ROOT / 'applications-proxy-state.json'
    enabled = settings(cfg).get('passwall2-tcp-all', False)
    if not enabled and not state_path.exists():
        return 'Proxy TCP ports unmanaged'
    state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state_path.parent / '.applications-proxy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if state_path.is_symlink():
            raise ValueError('Proxy state must not be a symbolic link')
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        if not enabled and not state:
            return 'Proxy TCP ports unmanaged'
        active = backend.enabled()
        if enabled and not active:
            raise ValueError('PassWall2 is not enabled; disable automatic TCP port management or enable it manually')
        current = backend.read()
        if state and current != state['after']:
            raise ValueError('PassWall2 TCP ports changed externally; refusing to overwrite them')
        before = state.get('before', current)
        desired = '1:65535' if enabled else before
        if current != desired:
            atomic_json(state_path.parent / 'backups' / ('applications-proxy-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'), {'before': current, 'after': desired})
            try:
                backend.write(desired)
                if active:
                    backend.restart()
                atomic_json(state_path, {'before': before, 'after': desired} if enabled else {})
            except Exception:
                backend.write(current)
                if active:
                    backend.restart()
                raise
        else:
            atomic_json(state_path, {'before': before, 'after': desired} if enabled else {})
        return 'Proxy TCP ports ' + ('managed: 1:65535' if enabled else 'restored')


def diagnose(cfg):
    address = settings(cfg).get('diagnostic-ip', '')
    ipaddress.IPv4Address(address)
    api = Api(cfg)
    networks = []
    for group in api.rows('route_object'):
        if 'TGClient' in group.get('group_name', ''):
            networks.extend(ipaddress.ip_network(row['ip'], strict=False) for row in group.get('group_value', []))
    rows = api.call('monitor_lanip', 'show', {'TYPE': 'conn,conn_num', 'ip': address, 'limit': '0,1000'}).get('results', {}).get('conn', [])
    selected = []
    for row in rows:
        try:
            telegram = any(ipaddress.ip_address(row.get('dst_addr', '')) in net for net in networks)
        except ValueError:
            telegram = False
        domain = row.get('domain', '').lower()
        ai = any(domain == suffix or domain.endswith('.' + suffix) for suffix in ('openai.com', 'chatgpt.com', 'oaistatic.com', 'oaiusercontent.com', 'oaistatsig.com'))
        if telegram or ai or row.get('dst_port') == 853:
            selected.append({key: row.get(key) for key in ('domain', 'dst_addr', 'dst_port', 'interface', 'status', 'total_up', 'total_down')})
    return '终端 ' + address + ' 的应用连接：\n' + json.dumps(selected, ensure_ascii=False, indent=2) + '\n连接建立和流量返回不能替代实际发送消息测试。853 连接可提示核对私人 DNS。'
