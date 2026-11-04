"""Exercise the installed core and wrapper against loopback-only mock services."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, '/usr/libexec/ikuai-bypass-python')
import yaml

rows = {
    'route_object': [{'id': 1, 'type': 0, 'group_name': 'Clients', 'tagname': 'Clients', 'group_id': 'IPGP1', 'group_value': [{'ip': '192.0.2.0/24', 'comment': ''}], 'ref_count': 0}],
    'stream_domain': [], 'stream_ipport': [],
}
events = []
empty = ''
identity = 100


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, value):
        value.setdefault('message', 'Success')
        payload = json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        events.append(('download', self.path))
        payload = {'/gfw': b'www.example.com\n', '/tg': b'149.154.160.0/20\n2001:b28:f23d::/48\n', '/ai': b'chatgpt.com\noaistatic.com\n'}.get(self.path)
        if payload is None:
            self.send_error(500, 'Inactive example must not be downloaded')
            return
        if self.path == '/' + empty:
            payload = b''
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        global identity
        request = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        if self.path == '/Action/login':
            self.reply({'code': 0})
            return
        func, action, param = request['func_name'], request['action'], request['param']
        events.append((func, action, copy.deepcopy(param)))
        if func not in rows:
            self.reply({'code': 1, 'message': 'Unexpected API function'})
            return
        if action == 'show':
            self.reply({'code': 0, 'results': {'data': copy.deepcopy(rows[func]), 'total': len(rows[func])}})
        elif action == 'add':
            identity += 1
            row = dict(param, id=identity)
            if func == 'route_object':
                row.update(group_id='IPGP' + str(identity), tagname=row['group_name'], ref_count=0)
            rows[func].append(row)
            self.reply({'code': 0, 'rowid': identity})
        elif action == 'edit':
            next(r for r in rows[func] if r['id'] == int(param['id'])).update(param)
            self.reply({'code': 0})
        elif action == 'del':
            ids = {int(value) for value in str(param['id']).split(',')}
            rows[func][:] = [r for r in rows[func] if r['id'] not in ids]
            self.reply({'code': 0})
        else:
            self.reply({'code': 1, 'message': 'Unexpected API action'})


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = 'http://127.0.0.1:' + str(server.server_port)
with tempfile.TemporaryDirectory(prefix='ikb-applications-probe-') as directory:
    cfg = yaml.safe_load(Path('/etc/ikuai-bypass/config.yml').read_text())
    cfg.update({'ikuai-url': base, 'username': 'mock', 'password': 'mock', 'github-proxy': '', 'mode': 'ispdomain', 'run-mode': 'once', 'AddWait': '1ms', 'AddErrRetryWait': '1ms'})
    cfg.setdefault('webui', {})['enable'] = False
    cfg['proxy'] = {'mode': 'system', 'url': ''}
    cfg['custom-isp'] = []
    cfg['ipv6-group'] = []
    cfg['ip-group'] = [{'tag': 'InactiveExample', 'url': base + '/must-not-download'}]
    cfg['stream-ipport'] = [{'opt-tagname': 'InactiveExample', 'type': '0', 'interface': 'wan1', 'nexthop': '', 'src-addr': '192.0.2.0/24', 'src-addr-opt-ipgroup': '', 'src-addr-inv': 0, 'ip-group': 'InactiveExample', 'dst-addr-inv': 0, 'prio': 31, 'mode': 1, 'ifaceband': 0, 'protocol': 'any'}]
    cfg['stream-domain'] = [{'tag': 'gfw', 'url': base + '/gfw', 'interface': 'wan2', 'src-addr': '', 'src-addr-opt-ipgroup': 'Clients'}]
    cfg['openwrt-addons'] = {'applications': {'telegram-enabled': True, 'chatgpt-enabled': True, 'anchor-tag': 'gfw', 'telegram-url': base + '/tg', 'chatgpt-url': base + '/ai'}}
    path = Path(directory) / 'config.yml'

    def run(label):
        events.clear()
        raw = yaml.safe_dump(cfg)
        path.write_text(raw)
        result = subprocess.run([os.environ.get('IKB_GUARD_RUNNER', '/usr/libexec/ikuai-bypass-guard'), str(path), '-r', 'once'], capture_output=True, text=True, timeout=40)
        assert path.read_text() == raw, 'Wrapper changed original configuration'
        assert not any(e[0] == 'download' and e[1] == '/must-not-download' for e in events)
        print(json.dumps({'case': label, 'exit': result.returncode, 'downloads': [e[1] for e in events if e[0] == 'download'], 'domain_rules': len(rows['stream_domain']), 'ip_groups': len(rows['route_object']), 'port_rules': len(rows['stream_ipport'])}), flush=True)
        if not empty:
            assert result.returncode == 0 and 'UPDATE:更新失败' not in result.stdout + result.stderr, result.stdout + result.stderr
        else:
            assert result.returncode == 2, result.stdout + result.stderr

    run('enabled-wan2')
    assert len(rows['stream_domain']) == 2 and len(rows['stream_ipport']) == 1
    assert rows['stream_ipport'][0]['interface'] == 'wan2'
    assert rows['stream_ipport'][0]['src_addr']['object'][0]['gid'] == 'IPGP1'
    cfg['stream-domain'][0]['interface'] = 'wan5'
    run('follow-wan5-without-duplicates')
    assert len(rows['stream_domain']) == 2 and len(rows['stream_ipport']) == 1
    assert rows['stream_ipport'][0]['interface'] == 'wan5'
    assert next(r for r in rows['stream_domain'] if r['tagname'] == 'IKBChatGPT1')['interface'] == 'wan5'
    before = copy.deepcopy(rows['route_object'])
    empty = 'tg'
    run('empty-telegram-preserves-group')
    assert rows['route_object'] == before
    before = copy.deepcopy(next(r for r in rows['stream_domain'] if r['tagname'] == 'IKBChatGPT1'))
    empty = 'ai'
    run('empty-chatgpt-preserves-domain-rule')
    assert next(r for r in rows['stream_domain'] if r['tagname'] == 'IKBChatGPT1') == before
    empty = ''
    cfg['openwrt-addons'] = {}
    before = copy.deepcopy(rows['stream_ipport'])
    run('disabled-does-not-update-application-rules')
    assert rows['stream_ipport'] == before
    assert [e[1] for e in events if e[0] == 'download'] == ['/gfw']
    if '--cron' in sys.argv:
        cfg['openwrt-addons'] = {'applications': {'telegram-enabled': True, 'chatgpt-enabled': True, 'telegram-url': base + '/tg', 'chatgpt-url': base + '/ai'}}
        cfg['cron'] = '*/2 * * * * *'
        raw = yaml.safe_dump(cfg)
        path.write_text(raw)
        events.clear()
        command = [os.environ.get('IKB_GUARD_RUNNER', '/usr/libexec/ikuai-bypass-guard'), str(path), '-r', 'cronAft']
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(7)
        process.terminate()
        out, err = process.communicate(timeout=10)
        downloads = [e[1] for e in events if e[0] == 'download']
        assert downloads.count('/tg') >= 2 and downloads.count('/ai') >= 2, out + err
        assert len(rows['stream_domain']) == 2 and len(rows['stream_ipport']) == 1
        assert 'UPDATE:更新失败' not in out + err, out + err
        assert path.read_text() == raw
        print(json.dumps({'case': 'repeated-cron-updates-both-applications', 'telegram_downloads': downloads.count('/tg'), 'chatgpt_downloads': downloads.count('/ai'), 'no_duplicate_rules': True}), flush=True)
server.shutdown()
