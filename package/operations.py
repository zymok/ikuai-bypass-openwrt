#!/usr/bin/python3
import base64
import fcntl
import hashlib
import json
import os
import signal
import ssl
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener
sys.path.insert(0, str(Path(__file__).resolve().parent / 'ikuai-bypass-python'))
import yaml

CONFIG = Path('/etc/ikuai-bypass/config.yml')
LOG = Path('/tmp/ikuai-bypass-task.log')
PID = Path('/tmp/ikuai-bypass-task.pid')
LOCK = Path('/tmp/ikuai-bypass-task.lock')
EXPORT = Path('/tmp/ikuai-bypass-domains.tar.gz')

def reply(ok, message):
    print(json.dumps({'ok': ok, 'message' if ok else 'error': message}, ensure_ascii=False))

from ikb_subscription_guard import external_opener


def worker(action, fd, tag):
    handle = os.fdopen(fd)
    command = ['/usr/bin/ikuai-bypass', '-c', str(CONFIG)]
    with LOG.open('w', encoding='utf-8') as log:
        try:
            if action == 'once':
                command = ['/usr/libexec/ikuai-bypass-guard', str(CONFIG), '-r', 'once']
                result = subprocess.run(command, stdout=log, stderr=log, timeout=1800)
            elif action == 'clean':
                command += ['-r', 'clean', '--tag', tag]
                result = subprocess.run(command, stdout=log, stderr=log, timeout=1800)
            elif action == 'export':
                EXPORT.unlink(missing_ok=True)
                with tempfile.TemporaryDirectory(prefix='ikuai-bypass-export-') as folder:
                    command += ['-r', 'exportDomainSteamToTxt', '--exportPath', folder]
                    result = subprocess.run(command, stdout=log, stderr=log, timeout=1800)
                    if result.returncode == 0:
                        with tarfile.open(EXPORT, 'w:gz') as archive:
                            for path in sorted(Path(folder).rglob('*')):
                                if path.is_file():
                                    archive.add(path, arcname=str(path.relative_to(folder)))
            else:
                raise ValueError('Unsupported task')
            log.write('\nTask exit code: ' + str(result.returncode) + '\n')
        except Exception as error:
            log.write('\nTask failed: ' + str(error) + '\n')
    handle.close()

def start(action, tag):
    if subprocess.run(['pidof', 'ikuai-bypass'], stdout=subprocess.DEVNULL).returncode == 0:
        raise ValueError('请先停止定时服务，再执行单次任务，避免规则同步冲突。')
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise ValueError('已有任务正在执行，请稍后查看日志。')
    try:
        command = [sys.executable, str(Path(__file__).resolve()), 'worker', action, str(fd), tag]
        process = subprocess.Popen(command, start_new_session=True, pass_fds=(fd,), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        PID.write_text(str(process.pid))
    finally:
        os.close(fd)
    reply(True, '任务已在后台启动；在此页刷新查看日志。任务最长运行 30 分钟，完成后保持定时服务关闭。')

def main():
    os.umask(0o077)
    action = sys.argv[1]
    if action == 'busy':
        with LOCK.open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                sys.exit(0)
        sys.exit(1)
    if action == 'worker':
        worker(sys.argv[2], int(sys.argv[3]), sys.argv[4])
        return
    if action == 'logs':
        if LOG.exists():
            print('最近单次任务：\n' + '\n'.join(LOG.read_text(encoding='utf-8', errors='replace').splitlines()[-150:]))
        output = subprocess.run(['logread'], capture_output=True, text=True, timeout=5)
        print('\n定时服务日志：\n' + '\n'.join(line for line in output.stdout.splitlines() if 'ikuai-bypass' in line)[-20000:])
        return
    if action in ('once', 'export', 'clean'):
        tag = sys.argv[2].strip() if len(sys.argv) > 2 else ''
        if action == 'clean' and not tag:
            raise ValueError('清理需要指定规则标识。')
        start(action, tag)
        return
    if action == 'cancel':
        if PID.exists():
            pid = int(PID.read_text())
            cmdline = Path('/proc') / str(pid) / 'cmdline'
            if cmdline.exists() and str(Path(__file__).resolve()).encode() in cmdline.read_bytes():
                os.killpg(pid, signal.SIGTERM)
                reply(True, '后台任务已停止。')
                return
        raise ValueError('没有正在运行的后台任务。')
    cfg = yaml.safe_load(CONFIG.read_text(encoding='utf-8'))
    if action.startswith('whatsapp-'):
        from ikb_addon_whatsapp import run
        print(json.dumps(run(cfg, action), ensure_ascii=False))
        return
    if action == 'login':
        context = ssl._create_unverified_context() if cfg.get('ikuai-url-ignore-cert') else ssl.create_default_context()
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context))
        password = cfg['password']
        body = {'username': cfg['username'], 'passwd': hashlib.md5(password.encode()).hexdigest(), 'pass': base64.b64encode(('salt_11' + password).encode()).decode(), 'remember_password': ''}
        request = Request(cfg['ikuai-url'].rstrip('/') + '/Action/login', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        with opener.open(request, timeout=15) as response:
            result = json.loads(response.read(65536))
        if result.get('code', result.get('Result')) != 0:
            raise ValueError('爱快登录失败，请检查地址、账号密码和证书设置。')
        reply(True, '爱快登录成功。')
    elif action in ('proxy', 'fetch'):
        url = sys.argv[2] if action == 'fetch' else 'https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/release/gfw.txt'
        opener, url = external_opener(cfg, url)
        with opener.open(url, timeout=15) as response:
            content = response.read(1048577 if action == 'fetch' else 1024)
        if action == 'fetch':
            if len(content) > 1048576:
                raise ValueError('Configuration exceeds 1 MiB')
            raw = content.decode('utf-8-sig')
            if not isinstance(yaml.safe_load(raw), dict):
                raise ValueError('Expected YAML configuration mapping')
            print(json.dumps({'ok': True, 'raw': raw}))
        else:
            reply(True, '规则订阅下载连接成功。')
    else:
        raise ValueError('Unsupported operation')

try:
    main()
except Exception as error:
    reply(False, str(error))
    sys.exit(1)
