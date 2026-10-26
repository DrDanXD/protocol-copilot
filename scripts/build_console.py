"""Build the console.

    python scripts/build_console.py

console/index.html      full page. Served by the API at /, or open as a static site
                        next to snapshot.json (GitHub Pages).
console/dist/demo.html  single file with the snapshot embedded, for sharing as one link.
site/index.html         the same demo as a full page, deployed to GitHub Pages by CI.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
subprocess.run([sys.executable, str(ROOT / "scripts" / "export_snapshot.py")], check=True)
app = (ROOT / "console" / "app.html").read_text()
(ROOT / "console" / "index.html").write_text(
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    "</head>\n<body>\n" + app + "\n</body>\n</html>\n")
snap = (ROOT / "console" / "snapshot.json").read_text()
json.loads(snap)
embedded = app.replace("<script>window.__SNAPSHOT__ = null;</script>",
                       "<script>window.__SNAPSHOT__ = " + snap.replace("</", "<\\/") + ";</script>")
assert embedded != app, "snapshot placeholder not found"
(ROOT / "console" / "dist").mkdir(exist_ok=True)
(ROOT / "console" / "dist" / "demo.html").write_text(embedded)
(ROOT / "site").mkdir(exist_ok=True)
(ROOT / "site" / "index.html").write_text(
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    '<meta name="description" content="Protocol Copilot demo: AI-drafted care plans a clinician approves.">\n'
    "</head>\n<body>\n" + embedded + "\n</body>\n</html>\n")
print("built console/index.html, console/dist/demo.html and site/index.html")
