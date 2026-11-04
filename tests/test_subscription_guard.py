import importlib.util
import unittest
import os
import tempfile
from unittest.mock import patch
from pathlib import Path

spec = importlib.util.spec_from_file_location('guard', Path(__file__).resolve().parents[1] / 'package/subscription_guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class GuardTest(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'Real flock requires Linux/OpenWrt')
    def test_canonical_run_locked_before_core_start(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(guard, 'RUN_LOCK', Path(directory) / 'run.lock'):
            def work(*args):
                self.assertTrue(guard.running())
                with self.assertRaises(ValueError):
                    guard.run('/etc/ikuai-bypass/config.yml', [])
                return 0
            with patch.object(guard, '_run', side_effect=work):
                self.assertEqual(guard.run('/etc/ikuai-bypass/config.yml', []), 0)
            self.assertFalse(guard.running())

    def test_nonproduction_run_does_not_touch_production_lock(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(guard, 'RUN_LOCK', Path(directory) / 'run.lock'), patch.object(guard, '_run', return_value=0):
            self.assertEqual(guard.run('/tmp/mock-config.yml', []), 0)
            self.assertFalse(guard.RUN_LOCK.exists())

    def test_invalid_lists(self):
        for value in (b'', b'# comment\n', b'<html>Error</html>', b'error message', b'good.example.com\n<html>bad</html>', b'\xff'):
            with self.subTest(value=value), self.assertRaises((ValueError, UnicodeError)):
                guard.validate(value, 'stream-domain')

    def test_domain_comments_and_duplicates(self):
        raw, count = guard.validate(b'\xef\xbb\xbf# title\ngoogle.com # comment\ngoogle.com\n*.whatsapp.net\n', 'stream-domain')
        self.assertEqual(raw, b'google.com\n*.whatsapp.net\n')
        self.assertEqual(count, 2)

    def test_address_families(self):
        data = b'10.0.0.0/8\n2001:db8::/32\n'
        self.assertEqual(guard.validate(data, 'ip-group')[0], b'10.0.0.0/8\n')
        self.assertEqual(guard.validate(data, 'ipv6-group')[0], b'2001:db8::/32\n')
        with self.assertRaises(ValueError):
            guard.validate(b'10.0.0.0/8', 'ipv6-group')

    def test_original_configuration_not_modified(self):
        cfg = {'stream-domain': [{'tag': 'gfw', 'url': 'https://example.com/list'}], 'proxy': {'mode': 'custom', 'url': 'http://proxy:8080'}}
        with guard.Guard(cfg) as instance:
            staged = instance.configuration()
            self.assertTrue(staged['stream-domain'][0]['url'].startswith('http://127.0.0.1:'))
            self.assertEqual(cfg['stream-domain'][0]['url'], 'https://example.com/list')
            self.assertEqual(instance.cfg['proxy'], cfg['proxy'])


if __name__ == '__main__':
    unittest.main()
