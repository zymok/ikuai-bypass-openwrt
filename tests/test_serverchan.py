import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'package'))
import serverchan


class ServerChanTest(unittest.TestCase):
    config = {'serverchan': {'enabled': True, 'send-key': 'SCTtest12345678', 'title': '家里路由'}}

    def test_turbo_post_with_custom_title(self):
        with patch.object(serverchan, 'build_opener') as build:
            build.return_value.open.return_value = io.BytesIO(b'{"code":0}')
            title = serverchan.title_for(self.config, '微信推送测试')
            serverchan.send(self.config, title, '详情')
            request = build.return_value.open.call_args.args[0]
            self.assertEqual(request.get_method(), 'POST')
            self.assertEqual(request.full_url, 'https://sctapi.ftqq.com/SCTtest12345678.send')
            self.assertEqual(parse_qs(request.data.decode()), {'title': ['家里路由 · ikuaibypass 微信推送测试'], 'desp': ['详情']})
            self.assertTrue(any(isinstance(handler, serverchan.NoRedirect) for handler in build.call_args.args))

    def test_transport_error_redacts_key(self):
        with patch.object(serverchan, 'build_opener') as build:
            build.return_value.open.side_effect = OSError(self.config['serverchan']['send-key'])
            with self.assertRaises(ValueError) as error:
                serverchan.send(self.config, '测试', '')
            self.assertNotIn(self.config['serverchan']['send-key'], str(error.exception))

    def test_partial_failure_with_zero_core_exit(self):
        guard = SimpleNamespace(events=[
            ('stream-domain', 'private-tag', 'accepted', 17),
            ('ip-group', 'another-tag', 'rejected', 'TimeoutError'),
        ])
        results = serverchan.UpdateResults(self.config, guard, False)
        results.observe('2026/11/11 08:00:00 [DOMAIN:域名分流] [UPDATE:更新失败] api error: private https://192.0.2.1/token')
        with patch.object(serverchan, 'send') as send:
            results.finish(0)
            _, title, body = send.call_args.args
        self.assertEqual(title, '家里路由 · ikuaibypass 规则更新失败')
        self.assertIn('共 17 条', body)
        self.assertIn('拒绝 1 个订阅', body)
        self.assertIn('核心异常日志', body)
        self.assertIn('[GUARD:REJECT] IPv4 分组 · 订阅请求超时', body)
        self.assertIn('[UPDATE:更新失败] 爱快 API 返回错误', body)
        self.assertNotIn('private', body)
        self.assertNotIn('192.0.2.1', body)

    def test_scheduled_completion_ignores_module_banner_and_collects_late_errors(self):
        guard = SimpleNamespace(events=[('stream-domain', 'example', 'accepted', 1)])
        prefix = '2026/11/11 08:00:00 [SYS:系统组件] '
        with patch.object(serverchan.threading, 'Thread'), patch.object(serverchan.threading, 'Timer'):
            results = serverchan.UpdateResults(self.config, guard, True)
            results.observe(prefix + '[DONE:任务完成] module=ispdomain')
            results.observe(prefix + '[UPDATE:更新失败] Late API error')
            results.observe(prefix + '[DONE:任务完成] ISP and Domain streaming update tasks completed')
            results.observe(prefix + '[TASK:任务启动] module=ispdomain')
        success, body = results.queue.get_nowait()
        self.assertFalse(success)
        self.assertIn('核心异常日志', body)
        self.assertTrue(results.queue.empty())


if __name__ == '__main__':
    unittest.main()
