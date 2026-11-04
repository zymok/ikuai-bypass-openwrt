import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('config_helper', ROOT / 'package/config-helper.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

LEGACY = '''# legacy configuration
ikuai-url: http://192.0.2.1
username: admin
password: ""
cron: 0 7 * * *
run-mode: cronAft
mode: ispdomain
custom-isp: []
stream-domain: []
ip-group: []
ipv6-group: []
stream-ipport: []
MaxNumberOfOneRecords:
  Domain: 1000 # preserve this nested tail comment

'''


class ConfigUpgradeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        helper.CONFIG = Path(self.tmp.name) / 'config.yml'
        helper.SCHEMA = ROOT / 'package/schema.json'

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, raw, values):
        helper.CONFIG.write_text(raw, encoding='utf-8')
        request = {'kind': 'fields', 'original': raw, 'fields': {}, 'values': values, 'rules': [], 'additions': []}
        with patch.object(sys, 'argv', ['helper', 'save']), patch.object(sys, 'stdin', io.StringIO(json.dumps(request))), contextlib.redirect_stdout(io.StringIO()):
            helper.main()
        return helper.CONFIG.read_text(encoding='utf-8')

    def test_add_application_settings_to_legacy_yaml(self):
        text = self.save(LEGACY, {'openwrt-addons.applications.telegram-enabled': True, 'openwrt-addons.applications.dns-enabled': True})
        data, _, _ = helper.parse(text)
        self.assertTrue(data['openwrt-addons']['applications']['telegram-enabled'])
        self.assertTrue(data['openwrt-addons']['applications']['dns-enabled'])
        self.assertIn('preserve this nested tail comment', text)
        self.assertIn('# legacy configuration', text)

    def test_add_sibling_to_existing_whatsapp_settings(self):
        raw = LEGACY + 'openwrt-addons:\n  whatsapp:\n    enabled: true # keep WhatsApp\n'
        text = self.save(raw, {'openwrt-addons.applications.chatgpt-enabled': True})
        data, _, _ = helper.parse(text)
        self.assertTrue(data['openwrt-addons']['whatsapp']['enabled'])
        self.assertTrue(data['openwrt-addons']['applications']['chatgpt-enabled'])
        self.assertIn('keep WhatsApp', text)

    def test_default_options_do_not_rewrite_legacy_yaml(self):
        text = self.save(LEGACY, {'openwrt-addons.applications.telegram-enabled': False})
        self.assertEqual(text, LEGACY)

    def test_foreign_scalar_parent_is_not_overwritten(self):
        raw = LEGACY + 'openwrt-addons: custom-string\n'
        with self.assertRaises(ValueError):
            self.save(raw, {'openwrt-addons.applications.telegram-enabled': True})
        self.assertEqual(helper.CONFIG.read_text(encoding='utf-8'), raw)


if __name__ == '__main__':
    unittest.main()
