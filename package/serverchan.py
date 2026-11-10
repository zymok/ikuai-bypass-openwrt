import json
import re
import threading
from collections import Counter
from datetime import datetime
from queue import Full, Queue
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

GROUP_LABELS = {'stream-domain': '域名分流', 'custom-isp': '自定义运营商', 'ip-group': 'IPv4 分组', 'ipv6-group': 'IPv6 分组'}
DOWNLOAD_ERRORS = {
    'HTTPError': '订阅服务器返回 HTTP 错误',
    'URLError': '订阅连接失败',
    'TimeoutError': '订阅请求超时',
    'ValueError': '订阅内容未通过校验',
    'UnicodeDecodeError': '订阅编码无效',
    'IncompleteRead': '订阅响应不完整',
}


def core_error_summary(detail):
    text = detail.lower()
    if '502 bad gateway' in text and 'download error' in text:
        return '订阅被下载保护拒绝'
    if 'api error' in text:
        return '爱快 API 返回错误'
    if 'timeout' in text or 'timed out' in text:
        return '请求超时'
    if 'login' in text:
        return '爱快登录失败'
    if 'connect' in text:
        return '连接失败'
    return '具体错误见 LuCI 运行日志'


def settings(config):
    return config.get('serverchan', {})


def validate(config):
    options = settings(config)
    if not isinstance(options, dict):
        raise ValueError('Server 酱设置必须为映射。')
    key = options.get('send-key', '')
    if not isinstance(key, str) or (key and not re.fullmatch(r'SCT[A-Za-z0-9_-]{8,200}', key)):
        raise ValueError('请输入以 SCT 开头的 Server 酱 Turbo SendKey。')
    if options.get('enabled') and not key:
        raise ValueError('开启微信推送前请填写 SendKey。')
    title = options.get('title', '')
    if not isinstance(title, str) or len(title) > 48 or (title and title.splitlines() != [title]):
        raise ValueError('推送标题须为单行，最多 48 个字符。')


def title_for(config, suffix):
    validate(config)
    prefix = settings(config).get('title', '').strip()
    title = f'ikuaibypass {suffix}'
    return f'{prefix} · {title}' if prefix else title


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send(config, title, body):
    validate(config)
    key = settings(config).get('send-key')
    if not key:
        raise ValueError('请先填写并保存 Server 酱 SendKey。')
    request = Request(
        f'https://sctapi.ftqq.com/{key}.send',
        data=urlencode({'title': title, 'desp': body}).encode('ascii'),
    )
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=8) as response:
            result = json.loads(response.read(16384))
    except Exception:
        raise ValueError('无法取得 Server 酱响应，请检查路由器联网、证书和 SendKey。') from None
    if not isinstance(result, dict) or result.get('code') not in (0, '0'):
        raise ValueError('Server 酱拒绝了请求，请检查 SendKey、消息通道和额度。')


def notify(config, success, reason):
    try:
        title = title_for(config, '规则更新成功' if success else '规则更新失败')
        send(config, title, reason)
    except ValueError as error:
        print('[SERVERCHAN] ' + str(error), flush=True)
    else:
        print('[SERVERCHAN] 通知已由 Server 酱受理。', flush=True)


class UpdateResults:
    """Observe the fixed core's task markers and per-rule errors."""

    def __init__(self, config, guard, scheduled):
        self.config = config
        self.guard = guard
        self.scheduled = scheduled
        self.errors = Counter()
        self.error_log = Counter()
        self.completed = False
        self.event_offset = 0
        self.lock = threading.Lock()
        self.pending = None
        self.timer = None
        self.queue = Queue(maxsize=16)
        if scheduled:
            threading.Thread(target=self.deliver, daemon=True).start()

    def deliver(self):
        while True:
            notify(self.config, *self.queue.get())

    def report(self, failed, code=None):
        events = self.guard.events[self.event_offset:]
        self.event_offset += len(events)
        accepted = Counter()
        rejected = Counter()
        entries = Counter()
        download_log = Counter()
        for group, _, outcome, detail in events:
            if outcome == 'accepted':
                accepted[group] += 1
                entries[group] += detail
            else:
                rejected[group] += 1
                label = GROUP_LABELS.get(group, '订阅')
                message = DOWNLOAD_ERRORS.get(detail, '订阅下载或校验失败')
                download_log[f'[GUARD:REJECT] {label} · {message}'] += 1
        success = not (failed or self.errors or rejected)
        reason = '本轮规则更新已完成。'
        if rejected:
            reason = '本轮有订阅下载或校验失败，受影响的旧规则已保留。请查看 OpenWrt 更新日志。'
        elif not success:
            reason = '本轮有更新任务或规则写入失败，请查看 OpenWrt 更新日志。'
        details = [
            reason,
            '完成时间 ' + datetime.now().astimezone().isoformat(timespec='seconds'),
            '运行方式 ' + ('服务更新' if self.scheduled else '单次更新'),
        ]
        for group, label in GROUP_LABELS.items():
            if accepted[group] or rejected[group]:
                details.append(f'{label} · 通过 {accepted[group]} 个订阅，共 {entries[group]} 条 · 拒绝 {rejected[group]} 个订阅')
        if self.errors:
            summary = '、'.join(f'{tag.split(":", 1)[1]} {count} 条' for tag, count in self.errors.items())
            details.append('核心异常日志 ' + summary)
        if not success:
            log = download_log + self.error_log
            if code:
                log[f'[CORE:EXIT] 核心退出码 {code}'] += 1
            if log:
                excerpts = [f'- {line}（{count} 次）' for line, count in log.most_common(8)]
                if len(log) > len(excerpts):
                    excerpts.append('- 其余错误见 LuCI 运行日志。')
                details.append('**本轮错误日志摘录**\n\n' + '\n'.join(excerpts))
        self.errors.clear()
        self.error_log.clear()
        body = '\n\n'.join(details)
        if not self.scheduled:
            notify(self.config, success, body)
            return
        try:
            self.queue.put_nowait((success, body))
        except Full:
            print('[SERVERCHAN] 推送队列已满，跳过本轮通知。', flush=True)

    def observe(self, line):
        # Only parse the tag column, never rule names or URLs in log details.
        match = re.match(r'^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} \[[^\]]+\] \[([^\]]+)\] (.*)', line)
        tag, detail = match.groups() if match else ('', '')
        if line.startswith('[UPDATE:更新失败] '):
            tag = 'UPDATE:更新失败'
            detail = line.partition('] ')[2]
        with self.lock:
            if tag in ('UPDATE:更新失败', 'CLEAN:删除失败', 'VALID:参数校验'):
                self.errors[tag] += 1
                self.error_log[f'[{tag}] {core_error_summary(detail)}'] += 1
            if self.scheduled and detail.startswith('module='):
                if tag == 'TASK:任务启动':
                    self.flush_pending()
                elif tag in ('DONE:任务完成', 'TASK:任务失败'):
                    self.completed = True
                    self.pending = tag == 'TASK:任务失败'
                    if self.pending:
                        self.error_log[f'[{tag}] {core_error_summary(detail)}'] += 1
                    # The core forwards individual rule logs asynchronously.
                    self.timer = threading.Timer(0.5, self.settle)
                    self.timer.daemon = True
                    self.timer.start()

    def settle(self):
        with self.lock:
            if threading.current_thread() is self.timer:
                self.flush_pending()

    def flush_pending(self):
        if self.pending is not None:
            self.timer.cancel()
            failed = self.pending
            self.pending = None
            self.report(failed)

    def finish(self, code):
        if code < 0:
            return
        if not self.scheduled:
            self.report(code != 0, code)
        elif code and not self.completed:
            # An early service failure has no runtime task completion record.
            notify(self.config, False, f'更新服务启动或运行失败，请查看 OpenWrt 更新日志。\n\n[CORE:EXIT] 核心退出码 {code}')
