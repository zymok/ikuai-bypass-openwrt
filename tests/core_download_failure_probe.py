"""Run on OpenWrt/Linux against the installed binary; all endpoints are loopback mocks."""
import copy
import json
import os
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
sys.path.insert(0, '/usr/libexec/ikuai-bypass-python')
import yaml

events = []
scenario = ''
rows = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, value, status=200):
        value.setdefault('message', 'Success')
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        events.append(('download', scenario))
        if scenario == 'http503':
            self.reply({'error': 'unavailable'}, 503)
        else:
            self.send_response(200)
            if scenario == 'html':
                self.send_header('Content-Type', 'text/html')
            if scenario == 'truncated':
                self.send_header('Content-Length', '10000')
            self.end_headers()
            self.wfile.write({'empty': b'', 'invalid': b'# comment only\n', 'valid': b'new.example.com\n', 'html': b'<html>Error</html>', 'garbage': b'new.example.com\nnot a domain\n', 'truncated': b'new.example.com\n'}[scenario])

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        if self.path == '/Action/login':
            self.reply({'code': 0, 'Result': 10000})
            return
        func, action = request.get('func_name'), request.get('action')
        events.append((func, action))
        if action == 'show':
            self.reply({'code': 0, 'results': {'data': rows if func == 'stream_domain' else [], 'total': len(rows)}})
        else:
            self.reply({'code': 0, 'rowid': 100})


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = 'http://127.0.0.1:' + str(server.server_port)
with tempfile.TemporaryDirectory(prefix='ikb-failure-probe-') as directory:
    cfg = yaml.safe_load(Path('/etc/ikuai-bypass/config.yml').read_text())
    cfg.pop('openwrt-addons', None)
    cfg.setdefault('webui', {})['enable'] = False
    cfg.update({'ikuai-url': base, 'username': 'mock', 'password': 'mock', 'github-proxy': '', 'mode': 'ispdomain', 'run-mode': 'once', 'AddWait': '1ms', 'AddErrRetryWait': '1ms'})
    cfg['proxy'] = {'mode': 'system', 'url': ''}
    for key in ('custom-isp', 'ip-group', 'ipv6-group', 'stream-ipport'):
        cfg[key] = []
    cases = ('empty', 'valid') if '--cron' in sys.argv else ('refused', 'http503', 'empty', 'invalid', 'html', 'garbage', 'truncated', 'valid')
    for scenario in cases:
        rows = [{'id': i, 'enabled': 'yes', 'tagname': 'IKBprobe' + str(i), 'interface': 'wan2', 'comment': 'IkuaiBypass', 'src_addr': {'custom': [], 'object': []}, 'domain': {'custom': ['old' + str(i) + '.example.com'], 'object': []}, 'time': {'custom': [{'weekdays': '1234567', 'start_time': '00:00', 'end_time': '23:59'}], 'object': []}} for i in (1, 2)]
        events.clear()
        url = 'http://127.0.0.1:1/list.txt' if scenario == 'refused' else base + '/list.txt'
        cfg['stream-domain'] = [{'tag': 'probe', 'url': url, 'interface': 'wan2', 'src-addr': '', 'src-addr-opt-ipgroup': ''}]
        path = Path(directory) / 'config.yml'
        path.write_text(yaml.safe_dump(cfg))
        command = [os.environ.get('IKB_GUARD_RUNNER', '/usr/libexec/ikuai-bypass-guard'), str(path)] if '--guard' in sys.argv else ['/usr/bin/ikuai-bypass', '-c', str(path)]
        if '--cron' in sys.argv:
            cfg['cron'] = '*/2 * * * * *'
            path.write_text(yaml.safe_dump(cfg))
            process = subprocess.Popen(command + ['-r', 'cronAft'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            time.sleep(7)
            process.terminate()
            stdout, stderr = process.communicate(timeout=10)
            result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        else:
            result = subprocess.run(command + ['-r', 'once'], capture_output=True, text=True, timeout=40)
        mutations = [e for e in events if e[0] != 'download' and e[1] != 'show']
        print(json.dumps({'case': scenario, 'exit': result.returncode, 'events': events, 'mutations': mutations, 'log': [line for line in (result.stdout + result.stderr).splitlines() if any(token in line for token in ['obtained', 'download error', 'failed', 'deleted'])]}, ensure_ascii=False), flush=True)
        if '--guard' in sys.argv:
            if '--cron' in sys.argv:
                assert sum(e[0] == 'download' for e in events) >= 2, (result.stdout, result.stderr)
                assert bool(mutations) == (scenario == 'valid'), (result.stdout, result.stderr)
                continue
            if scenario == 'valid':
                assert result.returncode == 0 and ('stream_domain', 'edit') in mutations and ('stream_domain', 'del') in mutations, (result.stdout, result.stderr)
                assert events[0][0] == 'download'
            else:
                assert result.returncode == 2 and not mutations and '[GUARD:REJECT]' in result.stdout, (result.stdout, result.stderr)
server.shutdown()
