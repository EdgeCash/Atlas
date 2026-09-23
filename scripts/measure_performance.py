"""Measure the built site in a real browser, at real viewports.

    python scripts/measure_performance.py [--site site] [--json out.json]

Load time, Largest Contentful Paint, DOM content loaded and transfer size for
each page type at phone, tablet and desktop. Numbers come from the browser's
own Performance API and PerformanceObserver, not from a stopwatch around a
request - a static file served locally is fast to fetch and the question is
what the browser does with it afterwards.

Served over HTTP from a local server rather than from ``file://``, because
file:// skips the network stack entirely and produces timings that flatter.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import json
import socketserver
import statistics
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CHROMIUM = Path("/opt/pw-browsers/chromium")

#: name, width, height. The three the product is designed against.
VIEWPORTS = (("mobile", 390, 844), ("tablet", 834, 1112), ("desktop", 1440, 900))

#: Each page type once. Team and card pages are representative of 116 and 58
#: siblings built from the same template.
PAGES = (
    ("board", "index.html"),
    ("card", "ncaaf/central-michigan-chippewas-miami-hurricanes.html"),
    ("team", "team/georgia-bulldogs.html"),
    ("landing", "about.html"),
    ("research", "research.html"),
    ("status", "status.html"),
)

#: Repeats per measurement. Three is enough to see a stable median without
#: the run taking minutes.
RUNS = 3

#: The browser script. `largest-contentful-paint` is buffered so an entry that
#: fired before the observer attached is still seen.
PROBE = """
() => new Promise(resolve => {
  let lcp = 0;
  try {
    new PerformanceObserver(list => {
      for (const e of list.getEntries()) lcp = Math.max(lcp, e.startTime);
    }).observe({type: 'largest-contentful-paint', buffered: true});
  } catch (e) { /* unsupported */ }
  const done = () => requestAnimationFrame(() => setTimeout(() => {
    const nav = performance.getEntriesByType('navigation')[0] || {};
    const paints = {};
    for (const p of performance.getEntriesByType('paint')) paints[p.name] = p.startTime;
    resolve({
      lcp_ms: Math.round(lcp),
      fcp_ms: Math.round(paints['first-contentful-paint'] || 0),
      dcl_ms: Math.round(nav.domContentLoadedEventEnd || 0),
      load_ms: Math.round(nav.loadEventEnd || 0),
      transfer_bytes: nav.transferSize || 0,
      decoded_bytes: nav.decodedBodySize || 0,
      resources: performance.getEntriesByType('resource').length,
    });
  }, 250));
  if (document.readyState === 'complete') done();
  else window.addEventListener('load', done);
})
"""


@contextlib.contextmanager
def serve(directory: Path):
    """A local HTTP server for the duration of the measurement."""
    handler = functools.partial(_QuietHandler, directory=str(directory))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{httpd.server_address[1]}"
        finally:
            httpd.shutdown()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Silent, and tolerant of the browser hanging up mid-response.

    Chromium closes connections it no longer needs - a preloaded image the
    layout turned out not to need, say - and the stdlib server prints a
    traceback for each one. That noise is not a finding about the site.
    """

    def log_message(self, *args):  # noqa: A003 - silencing the base class
        pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True


def measure(site: Path) -> dict:
    results: dict[str, dict[str, dict]] = {}
    with serve(site) as base, sync_playwright() as pw:
        launch = {"executable_path": str(CHROMIUM)} if CHROMIUM.exists() else {}
        browser = pw.chromium.launch(**launch)
        for label, width, height in VIEWPORTS:
            results[label] = {}
            for name, rel in PAGES:
                if not (site / rel).exists():
                    continue
                samples = []
                for _ in range(RUNS):
                    context = browser.new_context(
                        viewport={"width": width, "height": height},
                        device_scale_factor=2 if label == "mobile" else 1,
                    )
                    page = context.new_page()
                    page.goto(f"{base}/{rel}", wait_until="load")
                    samples.append(page.evaluate(PROBE))
                    context.close()
                results[label][name] = {
                    key: int(statistics.median(s[key] for s in samples))
                    for key in samples[0]
                }
                print(f"  {label:8} {name:9} "
                      f"lcp {results[label][name]['lcp_ms']:5} ms  "
                      f"load {results[label][name]['load_ms']:5} ms  "
                      f"{results[label][name]['transfer_bytes'] / 1024:6.1f} KB  "
                      f"{results[label][name]['resources']:3} requests")
        browser.close()
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", type=Path, default=ROOT / "site")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    if not args.site.exists():
        raise SystemExit(f"no built site at {args.site} - run `make site` first")

    print(f"Atlas performance — {RUNS} runs, median\n")
    results = measure(args.site)
    if args.json:
        args.json.write_text(json.dumps(results, indent=2, sort_keys=True))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
