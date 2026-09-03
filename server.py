# -*- coding: utf-8 -*-
"""
সুন্নাহ কেয়ার — নিউরো গার্ড
ল্যান্ডিং পেজ + অর্ডার API + প্রো অ্যাডমিন প্যানেল (একটাই সার্ভারে)

চালানো:  python3 server.py   (বা python3 admin_server.py — অ্যাডমিন মূল পেজ)
লিংক:    /  → ল্যান্ডিং পেজ    /admin → অ্যাডমিন প্যানেল

পাসওয়ার্ড: ADMIN_PASSWORD এনভায়রনমেন্ট বা ডিফল্ট 'sunnah2026'
"""
import json, os, time, random, csv, io, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT  = os.path.dirname(os.path.abspath(__file__))
DATAF = os.path.join(ROOT, 'data', 'orders.json')
SETTF = os.path.join(ROOT, 'data', 'settings.json')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'sunnah2026')
STATUSES = {'pending','confirmed','shipping','delivered','hold','cancel','return','noanswer','refunded'}

def load_orders():
    try:
        with open(DATAF, encoding='utf-8') as f: return json.load(f)
    except Exception: return []

def save_orders(orders):
    os.makedirs(os.path.dirname(DATAF), exist_ok=True)
    with open(DATAF, 'w', encoding='utf-8') as f:
        json.dump(orders, f, ensure_ascii=False, indent=1)

def load_settings():
    try:
        with open(SETTF, encoding='utf-8') as f: return json.load(f)
    except Exception:
        return {'blocked_ips': [], 'telegram': {'token': '', 'chat': ''}}

def save_settings(s):
    os.makedirs(os.path.dirname(SETTF), exist_ok=True)
    with open(SETTF, 'w', encoding='utf-8') as f:
        json.dump(s, f, ensure_ascii=False, indent=1)

def telegram_send(token, chat, text):
    try:
        req = urllib.request.Request(
            'https://api.telegram.org/bot%s/sendMessage' % token,
            data=json.dumps({'chat_id': chat, 'text': text}).encode(),
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.status == 200
    except Exception:
        return False

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str): body = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _file(self, name, ctype):
        try:
            with open(os.path.join(ROOT, name), 'rb') as f: self._send(200, f.read(), ctype)
        except FileNotFoundError:
            self._send(404, 'Not found', 'text/plain; charset=utf-8')

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n <= 0: return {}
        try: return json.loads(self.rfile.read(n).decode())
        except Exception: return {}

    def _admin(self):
        q = urlparse(self.path).query
        key = self.headers.get('X-Admin-Key', '')
        if not key and q.startswith('key='): key = q[4:]
        return key.strip().lower() == ADMIN_PASSWORD.strip().lower()

    def _ip(self):
        f = self.headers.get('X-Forwarded-For', '')
        return f.split(',')[0].strip() if f else self.client_address[0]

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.end_headers()

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ('/', '/index.html'): self._file('index.html', 'text/html; charset=utf-8')
        elif p in ('/admin', '/admin/'): self._file('admin.html', 'text/html; charset=utf-8')
        elif p == '/api/ping':
            self._send(200, {'ok': True, 'server': 'sunnah-care'})
        elif p == '/api/orders':
            if not self._admin(): self._send(401, {'ok': False, 'msg': 'ভুল পাসওয়ার্ড'}); return
            self._send(200, {'ok': True, 'orders': load_orders(), 'settings': load_settings()})
        elif p == '/api/orders.csv':
            if not self._admin(): self._send(401, '\ufeffভুল পাসওয়ার্ড', 'text/csv; charset=utf-8'); return
            buf = io.StringIO(); w = csv.writer(buf)
            w.writerow(['Order ID','তারিখ','সময়','নাম','ফোন','ঠিকানা','পণ্য','দাম','স্ট্যাটাস','কুরিয়ার','IP','ম্যানুয়াল'])
            for o in load_orders():
                d, _, t = str(o.get('ts','')).partition(' ')
                w.writerow([o['id'], d, t, o.get('name'), o.get('phone'), o.get('address'),
                            o.get('product'), o.get('price'), o.get('status'),
                            o.get('courier',''), o.get('ip',''), 'হ্যাঁ' if o.get('manual') else ''])
            self._send(200, '\ufeff' + buf.getvalue(), 'text/csv; charset=utf-8')
        else:
            self._send(404, 'Not found', 'text/plain; charset=utf-8')

    def do_POST(self):
        p = urlparse(self.path).path
        d = self._body()
        orders = None

        if p == '/api/order':                                   # পাবলিক: ল্যান্ডিং পেজ
            ip = self._ip()
            st = load_settings()
            if ip in st.get('blocked_ips', []):
                self._send(403, {'ok': False, 'msg': 'ব্লকড'}); return
            if not d.get('name') or not d.get('phone'):
                self._send(400, {'ok': False}); return
            orders = load_orders()
            o = self._new_order(d, ip=ip)
            orders.insert(0, o); self._send(200, {'ok': True, 'id': o['id']})

        elif p == '/api/orders/add':                            # অ্যাডমিন: ম্যানুয়াল অর্ডার
            if not self._admin(): self._send(401, {'ok': False}); return
            if not d.get('name') or not d.get('phone'):
                self._send(400, {'ok': False, 'msg': 'নাম ও ফোন আবশ্যক'}); return
            orders = load_orders()
            o = self._new_order(d, ip='ম্যানুয়াল', manual=True,
                                status=d.get('status') if d.get('status') in STATUSES else 'pending')
            orders.insert(0, o); self._send(200, {'ok': True, 'id': o['id']})

        elif p == '/api/orders/status':                         # স্ট্যাটাস বদল
            if not self._admin(): self._send(401, {'ok': False}); return
            if d.get('status') not in STATUSES: self._send(400, {'ok': False}); return
            orders = load_orders()
            for o in orders:
                if o['id'] == d.get('id'): o['status'] = d['status']
            self._send(200, {'ok': True})

        elif p == '/api/orders/update':                         # পণ্য/দাম/কুরিয়ার/নোট বদল
            if not self._admin(): self._send(401, {'ok': False}); return
            orders = load_orders()
            for o in orders:
                if o['id'] == d.get('id'):
                    for k in ('product', 'courier', 'note'):
                        if k in d: o[k] = str(d.get(k) or '')[:120]
                    if 'price' in d:
                        try: o['price'] = int(d.get('price') or 0)
                        except Exception: pass
            self._send(200, {'ok': True})

        elif p == '/api/orders/delete':
            if not self._admin(): self._send(401, {'ok': False}); return
            orders = [o for o in load_orders() if o['id'] != d.get('id')]
            self._send(200, {'ok': True})

        elif p == '/api/orders/clear':                          # সব ডিলিট
            if not self._admin(): self._send(401, {'ok': False}); return
            orders = []
            self._send(200, {'ok': True, 'msg': 'সব অর্ডার ডিলিট হয়েছে'})

        elif p == '/api/ipblock':                               # IP ব্লক/আনব্লক
            if not self._admin(): self._send(401, {'ok': False}); return
            st = load_settings()
            ip = str(d.get('ip') or '').strip()
            if ip:
                bl = st.get('blocked_ips', [])
                if d.get('action') == 'unblock':
                    bl = [x for x in bl if x != ip]
                elif ip not in bl:
                    bl.append(ip)
                st['blocked_ips'] = bl; save_settings(st)
            self._send(200, {'ok': True, 'blocked': st.get('blocked_ips', [])})

        elif p == '/api/settings':                              # টেলিগ্রাম সেটিংস
            if not self._admin(): self._send(401, {'ok': False}); return
            st = load_settings()
            tg = st.get('telegram', {})
            if 'token' in d: tg['token'] = str(d.get('token') or '')[:100]
            if 'chat' in d: tg['chat'] = str(d.get('chat') or '')[:100]
            st['telegram'] = tg; save_settings(st)
            self._send(200, {'ok': True})

        elif p == '/api/telegram/send':                         # রিপোর্ট টেলিগ্রামে
            if not self._admin(): self._send(401, {'ok': False}); return
            st = load_settings(); tg = st.get('telegram', {})
            if not tg.get('token') or not tg.get('chat'):
                self._send(400, {'ok': False, 'msg': 'আগে টেলিগ্রাম সেটিংস (Bot Token ও Chat ID) দিন'}); return
            orders = load_orders()
            today = time.strftime('%Y-%m-%d')
            scope = d.get('scope') or 'today'
            lst = [o for o in orders if scope == 'all' or str(o.get('ts','')).startswith(today)]
            cnt = lambda s: len([o for o in lst if o.get('status') == s])
            rev = sum(o.get('price', 0) for o in lst if o.get('status') == 'delivered')
            txt = ['🛒 সুন্নাহ কেয়ার — অর্ডার রিপোর্ট',
                   '📅 ' + ('আজ ' + today if scope == 'today' else 'সব অর্ডার'),
                   'মোট: %d | পেন্ডিং: %d | কনফার্মড: %d | শিপিং: %d | ডেলিভারড: %d' %
                   (len(lst), cnt('pending'), cnt('confirmed'), cnt('shipping'), cnt('delivered')),
                   '💰 বিক্রি (ডেলিভারড): ৳%d' % rev, '—————————']
            for i, o in enumerate(lst[:50], 1):
                txt.append('%d. %s — %s — %s — %s' % (i, o.get('name'), o.get('phone'), o.get('product'), o.get('status')))
            ok = telegram_send(tg['token'], tg['chat'], '\n'.join(txt))
            self._send(200 if ok else 502, {'ok': ok, 'msg': 'পাঠানো হয়েছে ✅' if ok else 'টেলিগ্রামে পাঠানো ব্যর্থ — Token/Chat ID চেক করুন'})
        else:
            self._send(404, {'ok': False})

        if orders is not None:
            save_orders(orders)

    def _new_order(self, d, ip='', manual=False, status='pending'):
        return {
            'id': int(time.time() * 1000) + random.randint(0, 99),
            'ts': time.strftime('%Y-%m-%d %H:%M'),
            'name': str(d.get('name', ''))[:80],
            'phone': str(d.get('phone', ''))[:20],
            'address': str(d.get('address', ''))[:200],
            'product': str(d.get('product', ''))[:60],
            'price': int(d.get('price') or 0),
            'status': status,
            'ip': ip, 'courier': str(d.get('courier', '') or '')[:120],
            'note': str(d.get('note', '') or '')[:120], 'manual': manual,
        }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    os.makedirs(os.path.dirname(DATAF), exist_ok=True)
    srv = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    print('✅ সুন্নাহ কেয়ার সার্ভার চালু: http://localhost:' + str(port) + '/  |  অ্যাডমিন: /admin')
    srv.serve_forever()
