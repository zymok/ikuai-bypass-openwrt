import hashlib
import io
import json
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

root = Path(__file__).resolve().parents[1]
metadata = json.loads((root / 'vendor/UPSTREAM.json').read_text(encoding='utf-8'))
target = root / 'downloads/core/ikuai-bypass'
target.parent.mkdir(parents=True, exist_ok=True)
archive = root / 'downloads/core.zip'
if archive.exists():
    data = archive.read_bytes()
else:
    with urlopen(metadata['binary_url'], timeout=60) as response:
        data = response.read(32 * 1024 * 1024 + 1)
if hashlib.sha256(data).hexdigest() != metadata['binary_archive_sha256']:
    raise SystemExit('Upstream archive SHA-256 mismatch')
with ZipFile(io.BytesIO(data)) as bundle:
    names = [name for name in bundle.namelist() if Path(name).name == 'ikuai-bypass']
    if len(names) != 1:
        raise SystemExit('Expected exactly one core executable')
    binary = bundle.read(names[0])
if hashlib.sha256(binary).hexdigest() != metadata['binary_sha256']:
    raise SystemExit('Core executable SHA-256 mismatch')
archive.write_bytes(data)
target.write_bytes(binary)
target.chmod(0o755)
print('Verified upstream core: ' + metadata['tag'])
