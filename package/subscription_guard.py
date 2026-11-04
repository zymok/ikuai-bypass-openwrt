import copy
import ipaddress
import json
import os
import re
import secrets
import signal
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

import yaml

LIMIT = 32 * 1024 * 1024


def external_opener(cfg, url):
    if not url.startswith(('http://', 'https://')):
        raise ValueError('Expected HTTP or HTTPS URL')
    proxy = cfg.get('proxy', {})
    mode = proxy.get('mode', 'smart')
    if mode == 'smart' and cfg.get('github-proxy') and url.startswith(('https://raw.githubusercontent.com/', 'https://github.com/')):
        return build_opener(ProxyHandler({})), cfg['github-proxy'].rstrip('/') + '/' + url
    if mode in ('smart', 'custom') and proxy.get('url'):
        handlers = [ProxyHandler({'http': proxy['url'], 'https': proxy['url']})]
        if proxy.get('user'):
            from urllib.request import HTTPPasswordMgrWithDefaultRealm, ProxyBasicAuthHandler
            credentials = HTTPPasswordMgrWithDefaultRealm()
            credentials.add_password(None, proxy['url'], proxy['user'], proxy.get('pass', ''))
            handlers.append(ProxyBasicAuthHandler(credentials))
        return build_opener(*handlers), url
    return build_opener(), url


def validate(raw, group):
    text = raw.decode('utf-8-sig')
    output = []
    seen = set()
    for line in text.splitlines():
        value = line.split('#', 1)[0].strip()
        if not value:
            continue
        if group == 'stream-domain':
            if '_' in value:
                continue
            domain = value[2:] if value.startswith('*.') else value
            domain = domain.rstrip('.')
            ascii_domain = domain.encode('idna').decode('ascii')
            if len(ascii_domain) > 253 or not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in ascii_domain.split('.')):
                raise ValueError('Invalid domain list content')
        else:
            if '-' in value:
                first, last = [ipaddress.ip_address(part.strip()) for part in value.split('-', 1)]
                if first.version != last.version or int(first) > int(last):
                    raise ValueError('Invalid IP range')
                version = first.version
            else:
                version = ipaddress.ip_network(value, strict=False).version
            if (group == 'ipv6-group') != (version == 6):
                continue
        if value not in seen:
            output.append(value)
            seen.add(value)
    if not output:
        raise ValueError('No valid entries; preserving existing rules')
    return ('\n'.join(output) + '\n').encode('utf-8'), len(output)


def download(cfg, url, group):
    opener, target = external_opener(cfg, url)
    with opener.open(target, timeout=30) as response:
        if response.status != 200:
            raise ValueError('Subscription HTTP status is not 200')
        content_type = response.headers.get('Content-Type', '').lower()
        if any(kind in content_type for kind in ('text/html', 'application/json', 'application/xml')):
            raise ValueError('Subscription returned an error/document page')
        raw = response.read(LIMIT + 1)
        length = response.headers.get('Content-Length')
        if len(raw) > LIMIT or (length is not None and int(length) != len(raw)):
            raise ValueError('Subscription size limit or incomplete response')
    return validate(raw, group)


class Guard:
    def __init__(self, cfg, fetch=download):
        self.cfg = copy.deepcopy(cfg)
        self.fetch = fetch
        self.rejected = 0
        self.events = []
        self.routes = {}
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                entry = owner.routes.get(self.path)
                if entry is None:
                    self.send_error(404)
                    return
                group, tag, url = entry
                try:
                    raw, count = owner.fetch(owner.cfg, url, group)
                    owner.events.append((group, tag, 'accepted', count))
                    print('[GUARD:ACCEPT] ' + json.dumps({'group': group, 'tag': tag, 'entries': count}, ensure_ascii=False), flush=True)
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/plain; charset=utf-8')
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except Exception as error:
                    owner.rejected += 1
                    owner.events.append((group, tag, 'rejected', type(error).__name__))
                    print('[GUARD:REJECT] ' + json.dumps({'group': group, 'tag': tag, 'error_type': type(error).__name__, 'message': 'Download/validation failed; existing rules preserved'}, ensure_ascii=False), flush=True)
                    self.send_error(502, 'Subscription rejected; existing rules preserved')

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def configuration(self):
        staged = copy.deepcopy(self.cfg)
        for group in ('stream-domain', 'custom-isp', 'ip-group', 'ipv6-group'):
            for row in staged.get(group, []):
                path = '/' + secrets.token_urlsafe(32)
                self.routes[path] = (group, row.get('tag', ''), row['url'])
                row['url'] = 'http://127.0.0.1:' + str(self.server.server_port) + path
        staged['github-proxy'] = ''
        staged['proxy'] = {'mode': 'system', 'url': ''}
        return staged

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def run(config, args, binary='/usr/bin/ikuai-bypass'):
    cfg = yaml.safe_load(Path(config).read_text(encoding='utf-8'))
    from ikb_applications import prepare, settings, sync_dns, sync_proxy_ports
    original = cfg
    cfg = prepare(cfg)
    operation = args[args.index('-r') + 1] if '-r' in args else cfg.get('run-mode', 'cronAft')
    if operation in ('once', 'cron', 'cronAft'):
        if Path(config).resolve() == Path('/etc/ikuai-bypass/config.yml'):
            print('[APPS:PROXY] ' + sync_proxy_ports(original), flush=True)
            print('[APPS:DNS] ' + sync_dns(original), flush=True)
        elif settings(original).get('dns-enabled') or settings(original).get('passwall2-tcp-all'):
            raise ValueError('Local network management requires the installed canonical config path')
    if settings(original).get('telegram-enabled') or settings(original).get('chatgpt-enabled'):
        print('[APPS:MODE] ' + original.get('mode', 'ispdomain') + ' -> ' + cfg['mode'], flush=True)
    with Guard(cfg) as guard, tempfile.TemporaryDirectory(prefix='ikuai-bypass-guard-') as folder:
        path = Path(folder) / 'config.yml'
        path.write_text(yaml.safe_dump(guard.configuration(), allow_unicode=True, sort_keys=False), encoding='utf-8')
        path.chmod(0o600)
        env = dict(os.environ)
        for key in ('NO_PROXY', 'no_proxy'):
            env[key] = ','.join(filter(None, [env.get(key, ''), '127.0.0.1', 'localhost']))
        child = subprocess.Popen([binary, '-c', str(path)] + args, env=env)
        previous = {}
        def stop(signum, frame):
            if child.poll() is None:
                child.send_signal(signum)
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, stop)
        try:
            code = child.wait()
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
        return code if code else (2 if guard.rejected else 0)
