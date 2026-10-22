"""Local preview of site/ at http://127.0.0.1:5081 (this Mac only). Tells the browser not to cache,
so edits to pages and scripts show on reload. Not used for the published site.

    .venv/bin/python serve.py
"""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 5081
SITE = Path(__file__).resolve().parent / "site"


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    handler = functools.partial(NoCacheHandler, directory=str(SITE))
    print(f"Previewing {SITE} at http://127.0.0.1:{PORT} (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", PORT), handler).serve_forever()
