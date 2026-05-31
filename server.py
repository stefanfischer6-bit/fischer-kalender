#!/usr/bin/env python3
"""Local dev server: serves static files + proxies iCloud photo stream API."""

import json
import urllib.request
import urllib.error
from http.server import HTTPServer, SimpleHTTPRequestHandler

ICLOUD_TOKEN = 'B1fGI9HKKGNomeT'
BASE_HOST = 'p01-sharedstreams.icloud.com'


def icloud_post(host, path, body):
    url = f'https://{host}/{ICLOUD_TOKEN}/sharedstreams/{path}'
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Origin', 'https://www.icloud.com')
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()), r.headers.get('X-Apple-MMe-Host')
    except urllib.error.HTTPError as e:
        if e.code == 330:
            # iCloud uses 330 to signal a host redirect — read the JSON body
            body_data = json.loads(e.read())
            return body_data, body_data.get('X-Apple-MMe-Host')
        raise


def fetch_photos():
    host = BASE_HOST
    stream, redirect_host = icloud_post(host, 'webstream', {'streamCtag': None})
    if redirect_host:
        host = redirect_host
        stream, _ = icloud_post(host, 'webstream', {'streamCtag': None})

    photos = stream.get('photos', [])
    if not photos:
        return []

    guids = [p['photoGuid'] for p in photos]
    assets, _ = icloud_post(host, 'webasseturls', {'photoGuids': guids})
    items = assets.get('items', {})

    urls = []
    for photo in photos:
        derivatives = photo.get('derivatives', {})
        keys = sorted(derivatives.keys(), key=lambda k: -int(k) if k.isdigit() else 0)
        chosen = next((k for k in keys if k.isdigit() and int(k) <= 2048), keys[0] if keys else None)
        if not chosen:
            continue
        checksum = derivatives[chosen].get('checksum')
        loc = items.get(checksum)
        if not loc:
            continue
        url_loc = loc.get('url_location')
        url_path = loc.get('url_path', '')
        url = f"https://{url_loc}{url_path}" if url_loc else loc.get('url', '')
        if url:
            urls.append(url)

    return urls


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/photos':
            try:
                urls = fetch_photos()
                body = json.dumps({'photos': urls}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                err = json.dumps({'error': str(e)}).encode()
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(err)))
                self.end_headers()
                self.wfile.write(err)
        else:
            super().do_GET()

    def log_message(self, fmt, *args):
        pass  # suppress access log noise


if __name__ == '__main__':
    port = 8765
    print(f'Fischer Dashboard → http://localhost:{port}')
    HTTPServer(('', port), Handler).serve_forever()
