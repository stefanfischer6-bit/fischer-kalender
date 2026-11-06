// Cloudflare Worker: serves the family iCloud calendar with CORS headers so the
// dashboard (GitHub Pages) can read it straight from the browser.
//
// It only ever fetches the one calendar below — it is not an open proxy.
// Deploy: Cloudflare dashboard → Workers & Pages → Create → "Hello World" Worker
// → Edit code → replace everything with this file → Deploy.

const ICAL_URL =
  'https://p176-caldav.icloud.com/published/2/MjEyNDc1MTc1MjEyNDc1MXt1pLI_9q6RHSJMgFWwViSxkGTHGKkhHYB9zgorFGkLnDRmDKlzbSGK5e02Bu65fxiUcT5Nr4TP-lieTKE1SLo';

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Max-Age': '86400',
};

export default {
  async fetch(request) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS });
    }
    if (request.method !== 'GET') {
      return new Response('Method not allowed', { status: 405, headers: CORS });
    }

    let upstream;
    try {
      upstream = await fetch(ICAL_URL, { redirect: 'follow' });
    } catch (e) {
      return new Response(`Calendar fetch failed: ${e}`, { status: 502, headers: CORS });
    }
    if (!upstream.ok) {
      return new Response(`iCloud returned ${upstream.status}`, { status: 502, headers: CORS });
    }

    return new Response(await upstream.text(), {
      headers: {
        ...CORS,
        'Content-Type': 'text/calendar; charset=utf-8',
        'Cache-Control': 'no-store',
      },
    });
  },
};
