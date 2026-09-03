# -*- coding: utf-8 -*-
"""অ্যাডমিন প্যানেল আলাদা পোর্টে (root = admin লগইন পেজ)"""
import os
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse
import server

class AdminRootHandler(server.Handler):
    def do_GET(self):
        p = urlparse(self.path).path
        if p in ('/', '/index.html', '/admin', '/admin/'):
            self._file('admin.html', 'text/html; charset=utf-8')
            return
        server.Handler.do_GET(self)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    srv = ThreadingHTTPServer(('0.0.0.0', port), AdminRootHandler)
    print('✅ অ্যাডমিন প্যানেল চালু (পোর্ট ' + str(port) + ') — পাসওয়ার্ড: sunnah2026')
    srv.serve_forever()
