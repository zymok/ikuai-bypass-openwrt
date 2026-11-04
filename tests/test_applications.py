import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for name, file in [('ikb_addon_api', 'addon_api.py'), ('ikb_applications', 'applications.py')]:
    spec = importlib.util.spec_from_file_location(name, ROOT / 'package' / file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
apps = sys.modules['ikb_applications']


def config():
    return {'mode': 'ispdomain', 'stream-domain': [{'tag': 'gfw', 'url': 'https://example.com/gfw', 'interface': 'wan5', 'src-addr': '', 'src-addr-opt-ipgroup': 'Clients'}],
            'custom-isp': [], 'ip-group': [{'tag': 'Inactive', 'url': 'https://example.com/inactive'}],
            'stream-ipport': [{'opt-tagname': 'InactiveRoute'}], 'ipv6-group': [],
            'openwrt-addons': {'applications': {'telegram-enabled': True, 'chatgpt-enabled': True}}}


class PrepareTest(unittest.TestCase):
    def test_follow_wan_and_source_without_mutation(self):
        cfg = config()
        original = copy.deepcopy(cfg)
        staged = apps.prepare(cfg)
        self.assertEqual(cfg, original)
        self.assertEqual(staged['mode'], 'ii')
        route = staged['stream-ipport'][0]
        self.assertEqual(route['interface'], 'wan5')
        self.assertEqual(route['src-addr-opt-ipgroup'], 'Clients')
        cfg['stream-domain'][0].update(interface='wan2', **{'src-addr-opt-ipgroup': 'NewClients'})
        staged = apps.prepare(cfg)
        self.assertEqual(staged['stream-ipport'][0]['interface'], 'wan2')
        self.assertEqual(staged['stream-domain'][-1]['src-addr-opt-ipgroup'], 'NewClients')

    def test_does_not_activate_inactive_examples(self):
        staged = apps.prepare(config())
        self.assertEqual([r['tag'] for r in staged['ip-group']], ['TGClient'])
        self.assertEqual([r['opt-tagname'] for r in staged['stream-ipport']], ['TGClient'])

    def test_off_preserves_original(self):
        cfg = config()
        cfg['openwrt-addons'] = {}
        self.assertEqual(apps.prepare(cfg), cfg)

    def test_repeated_preparation_is_consistent(self):
        cfg = config()
        self.assertEqual(apps.prepare(cfg), apps.prepare(cfg))

    def test_reserved_tag_requires_adoption(self):
        cfg = config()
        cfg['stream-domain'].append(dict(cfg['stream-domain'][0], tag='ChatGPT'))
        with self.assertRaises(ValueError):
            apps.prepare(cfg)
        cfg['openwrt-addons']['applications']['adopt-existing'] = True
        staged = apps.prepare(cfg)
        self.assertEqual(sum(r['tag'] == 'ChatGPT' for r in staged['stream-domain']), 1)

    def test_ipv6_base_kept_without_extra_examples(self):
        cfg = config()
        cfg['mode'] = 'ipv6group'
        cfg['ipv6-group'] = [{'tag': 'ExistingV6', 'url': 'https://example.com/v6'}]
        staged = apps.prepare(cfg)
        self.assertEqual(staged['mode'], 'iip')
        self.assertEqual([r['tag'] for r in staged['stream-domain']], ['ChatGPT'])
        self.assertEqual(staged['ipv6-group'], cfg['ipv6-group'])

    def test_invalid_anchor_and_url(self):
        cfg = config()
        cfg['stream-domain'] = []
        with self.assertRaises(ValueError):
            apps.prepare(cfg)
        cfg = config()
        cfg['openwrt-addons']['applications']['chatgpt-url'] = 'file:///etc/shadow'
        with self.assertRaises(ValueError):
            apps.prepare(cfg)


class FakeFirewall:
    def __init__(self):
        self.value = None
        self.reloads = 0
        self.bad_dns = False
        self.fail_reload = False

    def read(self):
        return copy.deepcopy(self.value)

    def zone_exists(self, zone):
        return zone == 'lan'

    def lan(self):
        return '192.0.2.1'

    def write(self, values):
        self.value = copy.deepcopy(values)

    def reload(self):
        self.reloads += 1
        if self.fail_reload:
            self.fail_reload = False
            raise ValueError('Injected reload failure')

    def check_dns(self, address, port):
        if self.bad_dns:
            raise ValueError('Injected DNS health failure')


class FakeProxy:
    def __init__(self):
        self.value = '80,443'
        self.restarts = 0
        self.fail = False

    def read(self):
        return self.value

    def enabled(self):
        return True

    def write(self, value):
        self.value = value

    def restart(self):
        self.restarts += 1
        if self.fail:
            self.fail = False
            raise ValueError('Injected proxy restart failure')


@unittest.skipIf(os.name == 'nt', 'Real flock requires Linux/OpenWrt')
class NetworkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / 'state.json'
        self.cfg = config()
        self.opts = self.cfg['openwrt-addons']['applications']
        self.opts.update({'dns-enabled': True, 'passwall2-tcp-all': True})
        self.fw = FakeFirewall()

    def tearDown(self):
        self.tmp.cleanup()

    def sync(self):
        return apps.sync_dns(self.cfg, self.fw, self.state)

    def test_dns_enable_idempotence_and_disable(self):
        self.sync()
        self.assertEqual(self.fw.value['dest_ip'], '192.0.2.1')
        self.assertEqual(self.fw.value['proto'], 'tcp udp')
        self.sync()
        self.assertEqual(self.fw.reloads, 1)
        self.opts['dns-enabled'] = False
        self.sync()
        self.assertIsNone(self.fw.value)
        self.assertEqual(json.loads(self.state.read_text()), {})

    def test_dns_target_follows_local_lan_and_port(self):
        self.sync()
        self.fw.lan = lambda: '198.51.100.1'
        self.opts['dns-port'] = 5353
        self.sync()
        self.assertEqual(self.fw.value['dest_ip'], '198.51.100.1')
        self.assertEqual(self.fw.value['dest_port'], '5353')

    def test_bad_dns_leaves_firewall_unchanged(self):
        self.fw.bad_dns = True
        with self.assertRaises(ValueError):
            self.sync()
        self.assertIsNone(self.fw.value)
        self.assertEqual(self.fw.reloads, 0)

    def test_invalid_zone_is_rejected(self):
        self.opts['dns-zone'] = 'missing'
        with self.assertRaises(ValueError):
            self.sync()
        self.assertIsNone(self.fw.value)

    def test_dns_reload_failure_rolls_back(self):
        self.fw.fail_reload = True
        with self.assertRaises(ValueError):
            self.sync()
        self.assertIsNone(self.fw.value)
        self.assertFalse(self.state.exists())

    def test_dns_foreign_change_is_rejected(self):
        self.sync()
        self.fw.value['dest_port'] = '9999'
        with self.assertRaises(ValueError):
            self.sync()
        self.assertEqual(self.fw.value['dest_port'], '9999')

    def test_dns_existing_rule_needs_adoption(self):
        self.fw.value = apps.dns_target(self.cfg, self.fw)
        with self.assertRaises(ValueError):
            self.sync()
        self.opts['adopt-existing'] = True
        self.sync()
        self.assertEqual(self.fw.reloads, 0)
        self.assertTrue(self.state.exists())

    def test_proxy_restore_and_idempotence(self):
        proxy = FakeProxy()
        apps.sync_proxy_ports(self.cfg, proxy, self.state)
        apps.sync_proxy_ports(self.cfg, proxy, self.state)
        self.assertEqual(proxy.value, '1:65535')
        self.assertEqual(proxy.restarts, 1)
        self.opts['passwall2-tcp-all'] = False
        apps.sync_proxy_ports(self.cfg, proxy, self.state)
        self.assertEqual(proxy.value, '80,443')

    def test_proxy_failure_rolls_back(self):
        proxy = FakeProxy()
        proxy.fail = True
        with self.assertRaises(ValueError):
            apps.sync_proxy_ports(self.cfg, proxy, self.state)
        self.assertEqual(proxy.value, '80,443')
        self.assertFalse(self.state.exists())

    def test_proxy_foreign_change_is_rejected(self):
        proxy = FakeProxy()
        apps.sync_proxy_ports(self.cfg, proxy, self.state)
        proxy.value = '443'
        with self.assertRaises(ValueError):
            apps.sync_proxy_ports(self.cfg, proxy, self.state)

    def test_disabled_proxy_restore_does_not_start_it(self):
        proxy = FakeProxy()
        apps.sync_proxy_ports(self.cfg, proxy, self.state)
        proxy.enabled = lambda: False
        self.opts['passwall2-tcp-all'] = False
        apps.sync_proxy_ports(self.cfg, proxy, self.state)
        self.assertEqual(proxy.value, '80,443')
        self.assertEqual(proxy.restarts, 1)


if __name__ == '__main__':
    unittest.main()
