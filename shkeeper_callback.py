"""Minimal SHKeeper callback receiver for a bot running on the VPS host.

Important: SHKeeper itself runs inside Kubernetes, therefore 127.0.0.1 inside the
SHKeeper pod is NOT the host bot. Bind this receiver to 0.0.0.0 and point SHKeeper
to the VPS/node IP (or a proper HTTPS reverse proxy).

The callback NEVER credits a balance. It only acknowledges/logs the event. The bot
confirms payment through SHKeeper's authenticated invoice API.
"""

import hmac
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HOST = os.getenv("SHKEEPER_CALLBACK_HOST", "0.0.0.0")
PORT = int(os.getenv("SHKEEPER_CALLBACK_PORT", "8787"))
CALLBACK_PATH = "/shkeeper/callback"
MAX_BODY = 1024 * 1024
LOG_FILE = Path(__file__).with_name("shkeeper_callbacks.log")


def _load_secret() -> str:
    env = os.getenv("SHKEEPER_CALLBACK_SECRET", "")
    if env:
        return env
    try:
        cfg = json.loads(Path(__file__).with_name("config.json").read_text(encoding="utf-8"))
        return str((cfg.get("shkeeper") or {}).get("callback_secret", ""))
    except Exception:
        return ""


CALLBACK_SECRET = _load_secret()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("shkeeper_callback")


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, body: dict):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        parsed = urlsplit(self.path)
        if parsed.path != CALLBACK_PATH:
            self._json(404, {"status": "not_found"})
            return

        if CALLBACK_SECRET:
            supplied = (parse_qs(parsed.query).get("token") or [""])[0]
            if not hmac.compare_digest(str(supplied), CALLBACK_SECRET):
                self._json(403, {"status": "forbidden"})
                return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_BODY:
                self._json(413, {"status": "too_large"})
                return
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            with LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
            external_id = payload.get("external_id") if isinstance(payload, dict) else None
            logger.info("SHKeeper callback received for external_id=%s", external_id)
            self._json(200, {"status": "success"})
        except Exception:
            logger.exception("Failed to process SHKeeper callback")
            self._json(400, {"status": "error"})

    def log_message(self, fmt, *args):
        logger.debug(fmt, *args)


if __name__ == "__main__":
    logger.info("Listening on http://%s:%s%s", HOST, PORT, CALLBACK_PATH)
    if not CALLBACK_SECRET:
        logger.warning("No callback_secret configured; endpoint is unauthenticated")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
