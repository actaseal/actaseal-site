"""Captures index.html at 375/768/1280px via Playwright, to check the
mobile layout. Serves the repo over a
throwaway local HTTP server so relative asset paths resolve exactly as they
would on the real site."""
import http.server
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "tests" / "screenshots"

WIDTHS = [375, 768, 1280]


def serve():
    handler = http.server.SimpleHTTPRequestHandler
    httpd = socketserver.TCPServer(("127.0.0.1", 8934), handler, bind_and_activate=False)
    httpd.allow_reuse_address = True
    httpd.server_bind()
    httpd.server_activate()
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def main():
    import os
    os.chdir(REPO_ROOT)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    httpd = serve()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed", file=sys.stderr)
        return 1
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in WIDTHS:
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.goto("http://127.0.0.1:8934/index.html")
            page.wait_for_load_state("networkidle")
            out = OUT_DIR / f"landing-{width}.png"
            page.screenshot(path=str(out), full_page=True)
            print(f"wrote {out}")
            page.close()
        browser.close()
    httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
