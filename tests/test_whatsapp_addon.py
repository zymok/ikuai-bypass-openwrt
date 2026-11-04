import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import fcntl
except ImportError:
    raise unittest.SkipTest('Run addon tests on Linux/OpenWrt: real flock is required')

ROOT = Path(__file__).resolve().parents[1]
for name in ('api', 'whatsapp'):
    spec = importlib.util.spec_from_file_location('ikb_addon_' + name, ROOT / 'package' / ('addon_' + name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
api = sys.modules['ikb_addon_api']
wa = sys.modules['ikb_addon_whatsapp']


class Fake:
    def __init__(self):
        self.data = {'wan': [{'name': 'wan2'}, {'name': 'wan5'}], 'route_object': [],
                     'stream_domain': [], 'dns_replace': [],
                     'dns': [{'dns1': '202.96.128.86', 'dns2': '223.5.5.5'}],
                     'dhcp_server': [{'id': 1, 'gateway': '192.0.2.254', 'addr_pool': '192.0.2.1-192.0.2.252', 'dns1': '192.0.2.254', 'dns2': ''}]}
        self.calls = []
        self.identity = 20

    def rows(self, func, kind=None):
        return copy.deepcopy(self.data[func])

    def call(self, func, action, data):
        assert func != 'dns', 'Global DNS must never be written'
        self.calls.append((func, action, copy.deepcopy(data)))
        if action == 'add':
            self.identity += 1
            self.data[func].append(dict(data, id=self.identity))
            return {'rowid': self.identity}
        identity = int(data['id'])
        row = next(r for r in self.data[func] if r['id'] == identity)
        if action == 'edit':
            row.update(data)
        else:
            self.data[func].remove(row)
        return {}


class AddonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        wa.ROOT = Path(self.tmp.name)
        wa.STATE = wa.ROOT / 'state.json'
        self.fake = Fake()
        self.old_api = wa.Api
        wa.Api = lambda cfg: self.fake
        self.cfg = {'stream-domain': [{'tag': 'gfw', 'interface': 'wan5', 'src-addr': '192.0.2.0/24'}],
                    'openwrt-addons': {'whatsapp': {'enabled': True, 'dhcp-enabled': True}}}

    def tearDown(self):
        wa.Api = self.old_api
        self.tmp.cleanup()

    def test_preview_sync_follow_and_restore(self):
        before = copy.deepcopy(self.fake.data)
        wa.run(self.cfg, 'whatsapp-preview')
        self.assertEqual(self.fake.calls, [])
        wa.run(self.cfg, 'whatsapp-sync')
        calls = len(self.fake.calls)
        wa.run(self.cfg, 'whatsapp-sync')
        self.assertEqual(len(self.fake.calls), calls)
        self.cfg['stream-domain'][0]['interface'] = 'wan2'
        wa.run(self.cfg, 'whatsapp-sync')
        self.assertEqual(self.fake.data['stream_domain'][0]['interface'], 'wan2')
        self.cfg['openwrt-addons']['whatsapp']['enabled'] = False
        wa.run(self.cfg, 'whatsapp-sync')
        self.assertEqual(self.fake.data, before)

    def test_foreign_change_is_rejected(self):
        wa.run(self.cfg, 'whatsapp-sync')
        self.fake.data['stream_domain'][0]['interface'] = 'wan2'
        before = copy.deepcopy(self.fake.data)
        with self.assertRaises(ValueError):
            wa.run(self.cfg, 'whatsapp-sync')
        self.assertEqual(self.fake.data, before)

    def test_line_dns_moves_and_restores_existing(self):
        opts = self.cfg['openwrt-addons']['whatsapp']
        opts.update({'line-dns-enabled': True, 'line-dns': '192.168.88.1'})
        original = {'id': 8, 'enabled': 'yes', 'tagname': 'Original', 'interface': 'wan5', 'dns1': '8.8.8.8', 'dns2': '9.9.9.9', 'comment': ''}
        self.fake.data['dns_replace'] = [copy.deepcopy(original)]
        wa.run(self.cfg, 'whatsapp-sync')
        self.cfg['stream-domain'][0]['interface'] = 'wan2'
        wa.run(self.cfg, 'whatsapp-sync')
        self.assertEqual(self.fake.data['dns_replace'][0], original)
        self.assertEqual(self.fake.data['dns_replace'][1]['interface'], 'wan2')
        opts['enabled'] = False
        wa.run(self.cfg, 'whatsapp-sync')
        self.assertEqual(self.fake.data['dns_replace'], [original])

    def test_source_group_is_followed(self):
        self.fake.data['route_object'] = [{'type': 0, 'group_id': 'IPGP3', 'group_name': 'Clients', 'group_value': [{'ip': '192.0.2.0/24'}]}]
        self.cfg['stream-domain'][0]['src-addr-opt-ipgroup'] = 'Clients'
        wa.run(self.cfg, 'whatsapp-sync')
        source = self.fake.data['stream_domain'][0]['src_addr']
        self.assertEqual(source['custom'], [])
        self.assertEqual(source['object'], [{'type': 0, 'gid': 'IPGP3', 'gp_name': 'Clients'}])

    def test_failure_rolls_back(self):
        before = copy.deepcopy(self.fake.data)
        original = self.fake.call
        def fail(func, action, data):
            if func == 'dhcp_server' and action == 'edit':
                raise ValueError('Injected DHCP failure')
            return original(func, action, data)
        self.fake.call = fail
        with self.assertRaisesRegex(ValueError, 'Injected'):
            wa.run(self.cfg, 'whatsapp-sync')
        self.assertEqual(self.fake.data, before)

    def test_existing_rule_adoption(self):
        self.cfg['openwrt-addons']['whatsapp']['dhcp-enabled'] = False
        desired = wa.plan(self.fake, self.cfg, self.cfg['openwrt-addons']['whatsapp'], {})['domain']
        desired.update(id=7, tagname='OriginalWhatsApp', interface='wan2')
        self.fake.data['stream_domain'].append(copy.deepcopy(desired))
        with self.assertRaises(ValueError):
            wa.run(self.cfg, 'whatsapp-sync')
        self.cfg['openwrt-addons']['whatsapp']['adopt-existing'] = True
        wa.run(self.cfg, 'whatsapp-sync')
        self.cfg['openwrt-addons']['whatsapp']['enabled'] = False
        wa.run(self.cfg, 'whatsapp-sync')
        self.assertEqual(self.fake.data['stream_domain'], [desired])


if __name__ == '__main__':
    unittest.main()
