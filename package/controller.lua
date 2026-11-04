module('luci.controller.ikuai_bypass', package.seeall)

function index()
    entry({'admin', 'services', 'ikuai-bypass'}, form('ikuai_bypass'), _('iKuai Bypass'), 60)
    entry({'admin', 'services', 'ikuai-bypass', 'backup'}, call('backup')).leaf = true
    entry({'admin', 'services', 'ikuai-bypass', 'export'}, call('export')).leaf = true
end

function export()
    local http = require 'luci.http'
    local path = '/tmp/ikuai-bypass-domains.tar.gz'
    if not require('nixio.fs').access(path) then http.status(404); return end
    http.header('Content-Disposition', 'attachment; filename="ikuai-bypass-domains.tar.gz"')
    http.header('Cache-Control', 'no-store')
    http.prepare_content('application/octet-stream')
    http.write(require('nixio.fs').readfile(path) or '')
end

function backup()
    local http = require 'luci.http'
    http.header('Content-Disposition', 'attachment; filename="ikuai-bypass-config.yml"')
    http.header('Cache-Control', 'no-store')
    http.prepare_content('application/octet-stream')
    http.write(require('nixio.fs').readfile('/etc/ikuai-bypass/config.yml') or '')
end
