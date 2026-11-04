#!/usr/bin/python3
import io
import json
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'ikuai-bypass-python'))
import yaml
from ruamel.yaml import YAML

CONFIG = Path('/etc/ikuai-bypass/config.yml')
SCHEMA = Path('/usr/share/ikuai-bypass/schema.json')
FIELDS = ['ikuai-url', 'username', 'password', 'cron', 'run-mode', 'mode', 'github-proxy', 'ikuai-url-ignore-cert']

def schema():
    return json.loads(SCHEMA.read_text(encoding='utf-8'))

def get_value(data, path, default):
    value = data
    for key in path.split('.'):
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value

def typed(value, spec):
    expected = {'str': str, 'int': int, 'bool': bool}[spec.get('type', 'str')]
    if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
        raise ValueError('Invalid type: ' + spec.get('path', spec.get('key', 'value')))
    if 'choices' in spec and str(value) not in [choice[0] for choice in spec['choices']]:
        raise ValueError('Invalid option: ' + spec.get('path', spec.get('key', 'value')))
    return value

def parse(raw):
    parser = YAML(typ='rt', pure=True)
    parser.preserve_quotes = True
    parser.allow_duplicate_keys = False
    parser.indent(mapping=2, sequence=4, offset=2)
    parser.width = 4096
    document = parser.load(raw)
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError('Configuration must be a YAML mapping')
    for key in ['ikuai-url', 'username', 'password', 'cron']:
        if not isinstance(data.get(key), str):
            raise ValueError('Required string: ' + key)
    if not data['ikuai-url'].startswith(('http://', 'https://')):
        raise ValueError('Router URL must use HTTP or HTTPS')
    if data.get('run-mode', 'cronAft') not in ['cron', 'cronAft', 'once']:
        raise ValueError('Invalid run-mode')
    if data.get('mode', 'ispdomain') not in ['ispdomain', 'ipgroup', 'ipv6group', 'ii', 'ip', 'iip']:
        raise ValueError('Invalid mode')
    definitions = schema()
    for group in definitions['groups']:
        rows = data.get(group['key'], [])
        if not isinstance(rows, list):
            raise ValueError('Expected rule list: ' + group['key'])
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('Expected rule object: ' + group['key'])
            for field in group['fields']:
                if field['key'] in row:
                    typed(row[field['key']], field)
    for spec in definitions['settings']:
        value = get_value(data, spec['path'], None)
        if value is not None:
            typed(value, spec)
    return data, document, parser

def check_rule(row, definition):
    for field in definition['fields']:
        typed(row[field['key']], field)
    if 'url' in row and (not row['url'].startswith(('http://', 'https://')) or any(char.isspace() for char in row['url'])):
        raise ValueError('Rule URL must be an HTTP or HTTPS link without whitespace')
    if definition['key'] == 'stream-domain' and not row.get('interface', '').strip():
        raise ValueError('Domain rule requires an interface')
    if definition['key'] == 'stream-ipport':
        if not (row.get('opt-tagname', '').strip() or row.get('ip-group', '').strip()):
            raise ValueError('Port rule requires a name or IP group')
        target = 'interface' if row['type'] == '0' else 'nexthop'
        if not row.get(target, '').strip():
            raise ValueError('Port rule requires ' + target)

def write_config(raw, original):
    parse(raw)
    if CONFIG.is_symlink() or CONFIG.read_text(encoding='utf-8') != original:
        raise ValueError('Configuration changed; reload before saving')
    if raw == original:
        return
    fd, name = tempfile.mkstemp(prefix='.config-', suffix='.yml', dir=CONFIG.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, CONFIG)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def main():
    if CONFIG.is_symlink():
        raise ValueError('Symbolic link configuration is unsupported')
    raw = CONFIG.read_text(encoding='utf-8')
    data, document, parser = parse(raw)
    definitions = schema()
    if sys.argv[1] == 'read':
        values = {spec['path']: get_value(data, spec['path'], spec['default']) for spec in definitions['settings']}
        print(json.dumps({'ok': True, 'raw': raw, 'fields': {key: data.get(key, '') for key in FIELDS}, 'values': values, 'rules': {group['key']: data.get(group['key'], []) for group in definitions['groups']}, 'schema': definitions}))
        return
    req = json.load(sys.stdin)
    if req['kind'] == 'raw':
        updated = req['raw'].replace('\r\n', '\n')
    else:
        changed = False
        specs = {spec['path']: spec for spec in definitions['settings']}
        for key, value in (req.get('fields') or {}).items():
            if key not in FIELDS:
                raise ValueError('Unsupported field')
            if data.get(key) != value:
                document[key] = value
                changed = True
        for path, value in (req.get('values') or {}).items():
            if path not in specs:
                raise ValueError('Unsupported setting')
            typed(value, specs[path])
            if get_value(data, path, specs[path]['default']) == value:
                continue
            target = document
            parts = path.split('.')
            for part in parts[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            target[parts[-1]] = value
            changed = True
        groups = {group['key']: group for group in definitions['groups']}
        removals = {}
        seen = set()
        for row in req.get('rules', []):
            group, index = row['group'], row['index']
            if group not in groups or type(index) is not int or index < 0 or index >= len(data.get(group, [])) or (group, index) in seen:
                raise ValueError('Invalid rule reference')
            seen.add((group, index))
            if row.get('remove'):
                removals.setdefault(group, []).append(index)
                changed = True
                continue
            allowed = {field['key']: field for field in groups[group]['fields']}
            target = document[group][index]
            candidate = dict(target)
            for key, value in (row.get('fields') or {}).items():
                if key not in allowed:
                    raise ValueError('Unsupported rule field')
                typed(value, allowed[key])
                candidate[key] = value
            if candidate != dict(target):
                complete = {field['key']: candidate.get(field['key'], field['default']) for field in groups[group]['fields']}
                check_rule(complete, groups[group])
                for key, value in (row.get('fields') or {}).items():
                    if target.get(key, allowed[key]['default']) != value:
                        target[key] = value
                changed = True
        for group, indices in removals.items():
            for index in sorted(indices, reverse=True):
                del document[group][index]
            if not document[group]:
                document[group] = []
        for addition in req.get('additions', []):
            group = addition['group']
            if group not in groups:
                raise ValueError('Unsupported rule group')
            fields = {field['key']: field for field in groups[group]['fields']}
            row = {key: field['default'] for key, field in fields.items()}
            for key, value in (addition.get('fields') or {}).items():
                if key not in fields:
                    raise ValueError('Unsupported rule field')
                row[key] = typed(value, fields[key])
            check_rule(row, groups[group])
            if group not in document:
                document[group] = []
            if 'url' in row and any(all(existing.get(key) == row.get(key) for key in ('tag', 'url')) for existing in document[group]):
                continue
            document[group].append(row)
            changed = True
        if changed:
            if any(isinstance(token, yaml.tokens.AliasToken) for token in yaml.scan(raw)):
                raise ValueError('Use YAML editor for configuration containing aliases')
            out = io.StringIO()
            parser.dump(document, out)
            updated = out.getvalue()
        else:
            updated = raw
    write_config(updated, req['original'])
    print(json.dumps({'ok': True}))

try:
    main()
except Exception as error:
    print(json.dumps({'ok': False, 'error': str(error)}))
    sys.exit(1)
