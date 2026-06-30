"""Tiny local HTTP sink: receives article text from the browser and writes files.

The browser (with Cloudflare clearance) extracts MDPI article text and POSTs it
here, so full text goes browser -> localhost -> disk WITHOUT passing through the
agent's context. CORS is wide-open and localhost is exempt from mixed-content
blocking, so an https://www.mdpi.com page can POST to http://localhost.
"""
from __future__ import annotations
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

OUT = Path(__file__).resolve().parents[1] / "corpus" / "energies"
OUT.mkdir(parents=True, exist_ok=True)


class H(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        # health check + list
        self.send_response(200); self._cors()
        self.send_header("Content-Type", "text/plain; charset=utf-8"); self.end_headers()
        files = sorted(p.name for p in OUT.glob("*.txt"))
        self.wfile.write(("OK; %d files: %s" % (len(files), ", ".join(files))).encode("utf-8"))

    def do_POST(self):
        q = parse_qs(urlparse(self.path).query)
        name = (q.get("name", ["paper"])[0]).replace("/", "_").replace("\\", "_")
        if not name.endswith(".txt"):
            name += ".txt"
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode("utf-8", errors="replace")
        (OUT / name).write_text(body, encoding="utf-8")
        print(f"saved {name}: {len(body)} chars", flush=True)
        self.send_response(200); self._cors()
        self.send_header("Content-Type", "text/plain; charset=utf-8"); self.end_headers()
        self.wfile.write(f"saved {name} {len(body)}".encode("utf-8"))

    def log_message(self, *a):  # quiet
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"text_sink listening on http://localhost:{port}  -> {OUT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
