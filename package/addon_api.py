import base64
import hashlib
import http.cookiejar
import json
import os
import ssl
import tempfile
from pathlib import Path
from urllib.request import HTTPSHandler, HTTPCookieProcessor, ProxyHandler, Request, build_opener

ROOT = Path('/etc/ikuai-bypass')

class Api:
    def __init__(self, cfg):
        self.base = cfg['ikuai-url'].rstrip('/')
        context = ssl._create_unverified_context() if cfg.get('ikuai-url-ignore-cert') else ssl.create_default_context()
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()), HTTPSHandler(context=context))
        password = cfg['password']
        self.request('/Action/login', {'username': cfg['username'], 'passwd': hashlib.md5(password.encode()).hexdigest(), 'pass': base64.b64encode(('salt_11' + password).encode()).decode(), 'remember_password': ''})

    def request(self, path, data):
        request = Request(self.base + path, json.dumps(data).encode(), {'Content-Type': 'application/json'})
        with self.opener.open(request, timeout=15) as response:
            raw = response.read(4194305)
        if len(raw) > 4194304:
            raise ValueError('iKuai response exceeds 4 MiB')
        result = json.loads(raw)
        if result.get('code') != 0:
            raise ValueError('iKuai API rejected request: ' + str(result.get('message', 'unknown error')))
        return result

    def call(self, func, action, param):
        return self.request('/Action/call', {'func_name': func, 'action': action, 'param': param})

    def rows(self, func, kind='total,data'):
        return self.call(func, 'show', {'TYPE': kind, 'limit': '0,10000'}).get('results', {}).get('data', [])

def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.addon-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def canonical(value):
    if isinstance(value, dict):
        return {key: ([] if key in ('custom', 'object') and item == {} else canonical(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [canonical(item) for item in value]
    return value

def body(func, row):
    keys = {
        'stream_domain': ['enabled', 'tagname', 'interface', 'src_addr', 'domain', 'comment', 'time', 'prio'],
        'dns_replace': ['enabled', 'tagname', 'interface', 'dns1', 'dns2', 'comment'],
    }.get(func)
    if keys:
        return canonical({key: row[key] for key in keys if key in row})
    return {key: value for key, value in row.items() if key not in ('id', 'modified_time', 'ref_count', 'available', 'status')}

class Transaction:
    def __init__(self, api, state):
        self.api = api
        self.state = state
        self.undo = []

    def current(self, func, identity):
        return next((row for row in self.api.rows(func) if row['id'] == identity), None)

    def check_owned(self, record):
        row = self.current(record['func'], record['id'])
        if row is None or body(record['func'], row) != record['after']:
            raise ValueError('Managed configuration changed outside the addon; restore or reconcile it manually')
        return row

    def apply(self, func, desired, record=None, candidate=None):
        if record:
            current = self.check_owned(record)
            if body(func, current) == body(func, desired):
                return record
            identity = current['id']
            self.api.call(func, 'edit', dict(body(func, desired), id=identity))
            self.undo.append(('edit', func, identity, body(func, current), None))
            before = record['before']
        elif candidate:
            identity = candidate['id']
            before = candidate
            if body(func, candidate) != body(func, desired):
                self.api.call(func, 'edit', dict(body(func, desired), id=identity))
                self.undo.append(('edit', func, identity, body(func, candidate), None))
        else:
            result = self.api.call(func, 'add', body(func, desired))
            identity = result.get('rowid')
            if identity is None:
                raise ValueError('iKuai did not return the new resource ID')
            before = None
            self.undo.append(('del', func, identity, None, None))
        actual = self.current(func, identity)
        if actual is None or body(func, actual) != body(func, desired):
            raise ValueError('iKuai configuration verification failed')
        return {'func': func, 'id': identity, 'before': before, 'after': body(func, actual)}

    def restore(self, record):
        current = self.check_owned(record)
        func, identity = record['func'], record['id']
        if record['before'] is None:
            self.api.call(func, 'del', {'id': str(identity)})
            self.undo.append(('add', func, identity, body(func, current), record))
        else:
            self.api.call(func, 'edit', dict(body(func, record['before']), id=identity))
            self.undo.append(('edit', func, identity, body(func, current), None))

    def rollback(self):
        errors = []
        for action, func, identity, data, record in reversed(self.undo):
            try:
                if action == 'edit':
                    self.api.call(func, 'edit', dict(data, id=identity))
                elif action == 'del':
                    self.api.call(func, 'del', {'id': str(identity)})
                else:
                    result = self.api.call(func, 'add', data)
                    record['id'] = result['rowid']
                    for old in [self.state.get('domain'), self.state.get('line')] + self.state.get('dhcp', []):
                        if old and old['func'] == func and old['id'] == identity:
                            old['id'] = result['rowid']
            except Exception as error:
                errors.append(str(error))
        if errors:
            raise ValueError('Rollback incomplete: ' + '; '.join(errors))
