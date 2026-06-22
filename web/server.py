"""
Voice Harvester — cross-platform web GUI server.

A single, dependency-free (stdlib) local server that serves the browser UI and the
full pipeline, so the app runs identically on macOS, Windows, and Linux:

  GET  /                      the UI
  GET  /api/env               { ffmpeg, demucs, voice_engine, ollama }
  POST /api/analyze           { path } -> speakers + segments (AI diarization)
  POST /api/export-speaker    { path, speaker | indices, out } -> clean wav
  POST /api/clone             { ref, text, language? } -> spoken wav
  POST /api/ask               { prompt, model? } -> Ollama reply (LLM assist)
  GET  /file?path=...         stream a wav (for in-page audio preview)

Local + private. Run:  python web/server.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO))

import engine          # noqa: E402
import analyze         # noqa: E402
import clone           # noqa: E402

HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def _ollama_models() -> list[str]:
    try:
        import urllib.request
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        with urllib.request.urlopen(host + "/api/tags", timeout=3) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def _ollama_chat(prompt: str, model: str | None) -> str:
    import urllib.request
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    models = _ollama_models()
    if not models:
        return "[Ollama not running] Start Ollama to enable the assistant."
    model = model or next((m for m in models if m.split(":")[0] in
                           ("llama3.2", "qwen2.5", "llama3.1", "mistral")), models[0])
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                       "stream": False}).encode()
    try:
        req = urllib.request.Request(host + "/api/chat", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read().decode("utf-8"))
        return (d.get("message", {}) or {}).get("content", "").strip() or "(no reply)"
    except Exception as e:
        return f"[error] {e}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body: bytes, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def _read(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            return {}

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            self._send(200, (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif u.path == "/app.js":
            self._send(200, (ROOT / "app.js").read_bytes(), "application/javascript; charset=utf-8")
        elif u.path == "/api/env":
            self._json(200, {
                "ffmpeg": engine.have_ffmpeg(),
                "demucs": engine.have_demucs(),
                "voice_engine": clone.is_ready(),
                "languages": clone.LANGS,
                "ollama": _ollama_models(),
            })
        elif u.path == "/file":
            q = parse_qs(u.query)
            p = (q.get("path") or [""])[0]
            try:
                self._send(200, Path(p).read_bytes(), "audio/wav")
            except OSError:
                self._json(404, {"error": "not found"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        d = self._read()
        if u.path == "/api/analyze":
            path = (d.get("path") or "").strip()
            if not path or not os.path.isfile(path):
                self._json(400, {"ok": False, "error": "file not found"}); return
            self._json(200, analyze.analyze(path))
        elif u.path == "/api/export-speaker":
            path = (d.get("path") or "").strip()
            out = (d.get("out") or os.path.expanduser("~/VoiceHarvester_output/speaker.wav"))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            res = analyze.export_speaker(path, d.get("speaker", ""), out,
                                         pick_indices=d.get("indices"))
            self._json(200, res)
        elif u.path == "/api/clone":
            ref = (d.get("ref") or "").strip()
            text = (d.get("text") or "").strip()
            out = d.get("out") or os.path.expanduser("~/VoiceHarvester_output/cloned.wav")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            self._json(200, clone.speak(ref, text, out, language=d.get("language")))
        elif u.path == "/api/ask":
            self._json(200, {"reply": _ollama_chat((d.get("prompt") or "").strip(),
                                                    d.get("model"))})
        else:
            self._json(404, {"error": "not found"})


def serve(port=DEFAULT_PORT, open_browser=True):
    httpd = ThreadingHTTPServer((HOST, port), Handler)
    url = f"http://{HOST}:{port}"
    print(f"Voice Harvester · web UI at {url}")
    print(f"  ffmpeg={engine.have_ffmpeg()} demucs={engine.have_demucs()} "
          f"voice_engine={clone.is_ready()} ollama={bool(_ollama_models())}")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye.")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    serve(a.port, open_browser=not a.no_open)
