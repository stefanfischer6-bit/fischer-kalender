#!/usr/bin/env python3
"""Download the iCloud shared album into photos/ and write photos.json.

iCloud asset URLs are signed and expire after a few hours, so linking to them
directly breaks the slideshow between workflow runs. Instead the images are
downloaded once (named by their stable photoGuid), downscaled, and served from
the repo. photos.json only changes when the album itself changes.
"""

import io
import json
import os
import sys
import urllib.request
import urllib.error

ICLOUD_TOKEN = 'B1fGI9HKKGNomeT'
BASE_HOST = 'p01-sharedstreams.icloud.com'
OUT_FILE = 'photos.json'
PHOTO_DIR = 'photos'
MAX_EDGE = 1280      # px, longest side after downscaling
JPEG_QUALITY = 82

try:
    from PIL import Image, ImageOps
except ImportError:  # still works without Pillow, just keeps the original size
    Image = None


def icloud_post(host, path, body):
    url = f'https://{host}/{ICLOUD_TOKEN}/sharedstreams/{path}'
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Origin', 'https://www.icloud.com')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()), r.headers.get('X-Apple-MMe-Host')
    except urllib.error.HTTPError as e:
        if e.code == 330:
            # iCloud uses 330 to signal a host redirect — read the JSON body
            body_data = json.loads(e.read())
            return body_data, body_data.get('X-Apple-MMe-Host')
        raise


def list_album():
    """Return [(photoGuid, signed_url)] for every still image in the album."""
    host = BASE_HOST
    stream, redirect_host = icloud_post(host, 'webstream', {'streamCtag': None})
    if redirect_host:
        host = redirect_host
        stream, _ = icloud_post(host, 'webstream', {'streamCtag': None})

    photos = [p for p in stream.get('photos', []) if p.get('mediaAssetType') != 'video']
    if not photos:
        return []

    guids = [p['photoGuid'] for p in photos]
    assets, _ = icloud_post(host, 'webasseturls', {'photoGuids': guids})
    items = assets.get('items', {})

    result = []
    for photo in photos:
        derivatives = photo.get('derivatives', {})
        # Smallest rendition that is still at least MAX_EDGE wide, else the largest.
        # (Keys are pixel sizes; many photos only offer ~342 and ~2049-2731.)
        sizes = sorted(int(k) for k in derivatives if k.isdigit())
        if not sizes:
            continue
        chosen = next((s for s in sizes if s >= MAX_EDGE), sizes[-1])
        loc = items.get(derivatives[str(chosen)].get('checksum'))
        if not loc:
            continue
        url_loc = loc.get('url_location')
        url = f"https://{url_loc}{loc.get('url_path', '')}" if url_loc else loc.get('url', '')
        if url:
            result.append((photo['photoGuid'], url))
    return result


def download(url, dest):
    with urllib.request.urlopen(url, timeout=60) as r:
        raw = r.read()
    if Image is not None:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert('RGB')
        img.thumbnail((MAX_EDGE, MAX_EDGE))
        img.save(dest, 'JPEG', quality=JPEG_QUALITY, optimize=True, progressive=True)
    else:
        with open(dest, 'wb') as f:
            f.write(raw)


def main():
    album = list_album()
    if not album:
        # Don't wipe the existing slideshow because of an API hiccup
        print('No photos returned by iCloud — leaving photos/ untouched.')
        return 1

    os.makedirs(PHOTO_DIR, exist_ok=True)
    keep, added, failed = [], 0, 0
    for guid, url in album:
        name = f'{guid}.jpg'
        path = os.path.join(PHOTO_DIR, name)
        if not os.path.exists(path):
            try:
                download(url, path)
                added += 1
            except Exception as e:  # skip this one, try again next run
                print(f'  ! {guid}: {e}', file=sys.stderr)
                failed += 1
                continue
        keep.append(name)

    removed = 0
    for name in os.listdir(PHOTO_DIR):
        if name.endswith('.jpg') and name not in keep:
            os.remove(os.path.join(PHOTO_DIR, name))
            removed += 1

    # Sorted, not shuffled: the page shuffles itself, and a stable file means
    # the workflow only commits when the album actually changed.
    with open(OUT_FILE, 'w') as f:
        json.dump({'photos': [f'{PHOTO_DIR}/{n}' for n in sorted(keep)]}, f, indent=0)
        f.write('\n')
    print(f'{len(keep)} photos ({added} new, {removed} removed, {failed} failed)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
