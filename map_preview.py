"""Private preview of the members' map at http://127.0.0.1:5082 (this Mac only; never published).

Shows the newest map file from mapbuild/ on a simple map. Builds the file first if there isn't one yet.

    .venv/bin/python map_preview.py
"""
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 5082
ROOT = Path(__file__).resolve().parent
PAGE = ROOT / "preview" / "map-preview.html"
POINTER = ROOT / "mapbuild" / "map" / "current.json"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self.send(PAGE.read_bytes(), "text/html; charset=utf-8")
        elif path == "/data/map.json":
            key = json.loads(POINTER.read_text())["key"]
            self.send((ROOT / "mapbuild" / key).read_bytes(), "application/json")
        else:
            self.send_error(404)

    def send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if not POINTER.exists():
        subprocess.run([sys.executable, "-m", "pipeline.mapdata", "--no-geocode"], cwd=ROOT, check=True,
                       env={"PYTHONPATH": str(ROOT)})
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"The preview is already running. Open http://127.0.0.1:{PORT} in your browser.")
        sys.exit(0)
    print(f"Market Map preview at http://127.0.0.1:{PORT} (Ctrl+C to stop)")
    server.serve_forever()
