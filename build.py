import hashlib
import io
import json
import struct
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = '4.4.110-9'

def archive(files):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w:gz', format=tarfile.USTAR_FORMAT) as tar:
        directories = set()
        for name in files:
            parent = Path(name).parent
            while str(parent) != '.':
                directories.add(parent.as_posix())
                parent = parent.parent
        for name in sorted(directories, key=lambda path: (path.count('/'), path)):
            info = tarfile.TarInfo('./' + name + '/')
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            info.uid = info.gid = 0
            tar.addfile(info)
        for name, (content, mode) in files.items():
            info = tarfile.TarInfo('./' + name)
            info.size = len(content)
            info.mode = mode
            info.uid = info.gid = 0
            tar.addfile(info, io.BytesIO(content))
    return out.getvalue()

def text(name):
    return (ROOT / name).read_text(encoding='utf-8').replace('\r\n', '\n').encode()

binary = (ROOT / 'downloads/core/ikuai-bypass').read_bytes()
if binary[:4] != b'\x7fELF' or binary[4] != 2 or struct.unpack_from('<H', binary, 18)[0] != 62:
    raise ValueError('Expected x86_64 ELF binary')
config = text('package/default-config.yml').decode()
config = config.replace('password: admin888', 'password: ""', 1)
config = config.replace('  enable: true', '  enable: false')
files = {
    'usr/bin/ikuai-bypass': (binary, 0o755),
    'usr/libexec/ikuai-bypass-guard': (text('package/guard-runner.py'), 0o755),
    'usr/libexec/ikuai-bypass-python/ikb_subscription_guard.py': (text('package/subscription_guard.py'), 0o644),
    'usr/libexec/ikuai-bypass-config': (text('package/config-helper.py'), 0o755),
    'usr/libexec/ikuai-bypass-operations': (text('package/operations.py'), 0o755),
    'etc/init.d/ikuai-bypass': (text('package/ikuai-bypass.init'), 0o755),
    'etc/ikuai-bypass/config.yml': (config.encode(), 0o600),
    'usr/lib/lua/luci/controller/ikuai_bypass.lua': (text('package/controller.lua'), 0o644),
    'usr/lib/lua/luci/model/cbi/ikuai_bypass.lua': (text('package/form.lua'), 0o644),
    'usr/share/ikuai-bypass/LICENSE': (text('LICENSE'), 0o644),
    'usr/share/ikuai-bypass/schema.json': (text('package/schema.json'), 0o644),
}
for name in ('api', 'whatsapp'):
    files['usr/libexec/ikuai-bypass-python/ikb_addon_' + name + '.py'] = (text('package/addon_' + name + '.py'), 0o644)
for module in sorted((ROOT / 'package/vendor/yaml').glob('*.py')):
    files['usr/libexec/ikuai-bypass-python/yaml/' + module.name] = (module.read_bytes(), 0o644)
files['usr/share/ikuai-bypass/PyYAML-LICENSE'] = (text('package/vendor/PyYAML-LICENSE'), 0o644)
for module in sorted((ROOT / 'package/vendor/ruamel/yaml').glob('*.py')):
    files['usr/libexec/ikuai-bypass-python/ruamel/yaml/' + module.name] = (module.read_bytes(), 0o644)
files['usr/share/ikuai-bypass/ruamel-LICENSE'] = (text('package/vendor/ruamel-LICENSE'), 0o644)
control = f'''Package: luci-app-ikuai-bypass
Version: {VERSION}
Architecture: x86_64
Maintainer: zymok
Section: luci
Priority: optional
License: AGPL-3.0-only
Depends: luci-base, luci-compat, python3, ca-bundle
Installed-Size: {sum(len(value[0]) for value in files.values())}
Description: iKuai Bypass core, procd service and local LuCI configuration editor
Conflicts: ikuai-bypass
Source: https://github.com/zymok/ikuai-bypass-openwrt
'''.encode()
postinst = b'''#!/bin/sh
[ -n "$IPKG_INSTROOT" ] && exit 0
chmod 600 /etc/ikuai-bypass/config.yml
rm -f /tmp/luci-indexcache
rm -rf /tmp/luci-modulecache
exit 0
'''
prerm = b'''#!/bin/sh
[ -n "$IPKG_INSTROOT" ] && exit 0
/etc/init.d/ikuai-bypass stop
/etc/init.d/ikuai-bypass disable
exit 0
'''
package = archive({
    'debian-binary': (b'2.0\n', 0o644),
    'control.tar.gz': (archive({'control': (control, 0o644), 'conffiles': (b'/etc/ikuai-bypass/config.yml\n', 0o644), 'postinst': (postinst, 0o755), 'prerm': (prerm, 0o755)}), 0o644),
    'data.tar.gz': (archive(files), 0o644),
})
out = ROOT / 'dist' / f'luci-app-ikuai-bypass_{VERSION}_x86_64.ipk'
out.parent.mkdir(exist_ok=True)
out.write_bytes(package)
digest = hashlib.sha256(package).hexdigest()
out.with_suffix('.ipk.sha256').write_text(digest + '  ' + out.name + '\n')
print(json.dumps({'file': str(out), 'bytes': len(package), 'sha256': digest}))
