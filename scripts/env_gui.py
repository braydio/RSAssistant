#!/usr/bin/env python3
"""Lightweight local GUI for editing config/.env."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = BASE_DIR / "config"
ENV_PATH = CONFIG_DIR / ".env"
TEMPLATE_PATH = CONFIG_DIR / ".env.example"


def _parse_env_lines(lines: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            entries.append({"type": "blank", "raw": line})
            continue
        if stripped.startswith("#"):
            entries.append({"type": "comment", "raw": line})
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            entries.append(
                {
                    "type": "kv",
                    "key": key.strip(),
                    "value": value.strip(),
                }
            )
            continue
        entries.append({"type": "comment", "raw": line})
    return entries


def _load_env_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    entries = _parse_env_lines(path.read_text(encoding="utf-8").splitlines())
    values = {}
    for entry in entries:
        if entry["type"] == "kv":
            values[entry["key"]] = entry.get("value", "")
    return values


def _load_example_entries() -> list[dict[str, Any]]:
    if not TEMPLATE_PATH.exists():
        return []
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    return _parse_env_lines(text.splitlines())


def _load_entries() -> list[dict[str, Any]]:
    """Load entries from .env.example and overlay values from .env when present."""
    entries = _load_example_entries()
    env_values = _load_env_map(ENV_PATH)
    for entry in entries:
        if entry["type"] == "kv":
            entry["value"] = env_values.get(entry["key"], "")
    return entries


def _write_entries(
    entries: list[dict[str, Any]],
    updates: dict[str, str],
    extras: dict[str, str],
) -> None:
    output_lines: list[str] = []
    for entry in entries:
        if entry["type"] == "kv":
            key = entry["key"]
            value = updates.get(key, "")
            output_lines.append(f"{key}={value}")
        else:
            output_lines.append(entry.get("raw", ""))

    if extras:
        output_lines.append("")
        output_lines.append("# Extra keys from existing .env")
        for key, value in sorted(extras.items()):
            output_lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def _detect_field_type(value: str) -> str:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return "bool"
    if value.replace(".", "", 1).isdigit():
        return "number"
    return "text"


def _build_html(entries: list[dict[str, Any]]) -> str:
    fields = []
    for entry in entries:
        if entry["type"] != "kv":
            continue
        key = entry["key"]
        value = entry.get("value", "")
        field_type = _detect_field_type(value)
        fields.append(
            {
                "key": key,
                "value": value,
                "type": field_type,
            }
        )

    payload_json = json.dumps(fields)
    payload_literal = json.dumps(payload_json)
    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>RSAssistant Config</title>
  <style>
    :root {
      --bg: #1a1b26;
      --panel: #1f2335;
      --ink: #c0caf5;
      --muted: #a9b1d6;
      --accent: #7aa2f7;
      --accent-2: #bb9af7;
      --stroke: #2f334d;
      --shadow: rgba(0, 0, 0, 0.35);
    }
    [data-theme="nightfox"] {
      --bg: #192330;
      --panel: #1f2b3d;
      --ink: #cdcecf;
      --muted: #9da9a0;
      --accent: #82aaff;
      --accent-2: #ff9e64;
      --stroke: #2c3b4f;
      --shadow: rgba(0, 0, 0, 0.35);
    }
    [data-theme="rose-pine"] {
      --bg: #191724;
      --panel: #1f1d2e;
      --ink: #e0def4;
      --muted: #908caa;
      --accent: #eb6f92;
      --accent-2: #9ccfd8;
      --stroke: #26233a;
      --shadow: rgba(0, 0, 0, 0.4);
    }
    [data-theme="gruvbox"] {
      --bg: #282828;
      --panel: #32302f;
      --ink: #ebdbb2;
      --muted: #bdae93;
      --accent: #d79921;
      --accent-2: #fb4934;
      --stroke: #3c3836;
      --shadow: rgba(0, 0, 0, 0.45);
    }
    [data-theme="catppuccin"] {
      --bg: #1e1e2e;
      --panel: #27293d;
      --ink: #cdd6f4;
      --muted: #a6adc8;
      --accent: #89b4fa;
      --accent-2: #f5c2e7;
      --stroke: #313244;
      --shadow: rgba(0, 0, 0, 0.4);
    }
    [data-theme="solarized"] {
      --bg: #002b36;
      --panel: #073642;
      --ink: #fdf6e3;
      --muted: #93a1a1;
      --accent: #2aa198;
      --accent-2: #b58900;
      --stroke: #0f3f49;
      --shadow: rgba(0, 0, 0, 0.4);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Palatino Linotype", "Book Antiqua", Palatino, serif;
      color: var(--ink);
      background: radial-gradient(circle at top, rgba(255,255,255,0.04) 0%, var(--bg) 65%);
    }
    header {
      padding: 32px 20px 12px;
      text-align: center;
    }
    header h1 {
      margin: 0;
      font-size: 28px;
      letter-spacing: 0.5px;
    }
    header p {
      margin: 8px auto 0;
      max-width: 720px;
      color: var(--muted);
    }
    main {
      max-width: 960px;
      margin: 0 auto;
      padding: 16px 20px 48px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--stroke);
      border-radius: 16px;
      box-shadow: 0 10px 30px var(--shadow);
      padding: 24px;
      animation: fadeIn 0.4s ease;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
      margin-top: 16px;
    }
    label {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
      display: block;
      margin-bottom: 6px;
    }
    input, select {
      width: 100%;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--stroke);
      font-family: "Fira Mono", "Cascadia Mono", "Courier New", monospace;
      font-size: 14px;
      background: rgba(255,255,255,0.04);
      color: var(--ink);
    }
    select {
      appearance: none;
      background-image: linear-gradient(45deg, transparent 50%, var(--accent) 50%),
        linear-gradient(135deg, var(--accent) 50%, transparent 50%);
      background-position: calc(100% - 18px) calc(1em + 2px), calc(100% - 13px) calc(1em + 2px);
      background-size: 5px 5px, 5px 5px;
      background-repeat: no-repeat;
    }
    .actions {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 24px;
      gap: 12px;
      flex-wrap: wrap;
    }
    .toolbar {
      display: flex;
      justify-content: flex-end;
      gap: 12px;
      margin-bottom: 16px;
      align-items: center;
    }
    .toolbar label {
      font-size: 11px;
      margin-bottom: 0;
    }
    button {
      background: var(--accent);
      color: #fff;
      border: none;
      padding: 12px 20px;
      border-radius: 999px;
      font-size: 14px;
      cursor: pointer;
      letter-spacing: 0.04em;
      box-shadow: 0 10px 20px rgba(212, 93, 60, 0.25);
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    button:hover {
      transform: translateY(-1px);
      box-shadow: 0 14px 24px rgba(212, 93, 60, 0.3);
    }
    .status {
      color: var(--muted);
      font-size: 13px;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }
  </style>
</head>
<body>
  <header>
    <h1>RSAssistant Configuration</h1>
    <p>Edit <code>config/.env</code> safely in one place. Values are written locally to this machine.</p>
  </header>
  <main>
    <div class="card">
      <div class="toolbar">
        <label for="themeSelect">Theme</label>
        <select id="themeSelect"></select>
      </div>
      <div id="fields" class="grid"></div>
      <div class="actions">
        <button id="saveBtn">Save .env</button>
        <span id="status" class="status"></span>
      </div>
    </div>
  </main>
  <script>
    const fields = JSON.parse(__PAYLOAD__);
    const container = document.getElementById('fields');
    const status = document.getElementById('status');
    const themeSelect = document.getElementById('themeSelect');
    const themes = [
      { id: 'nightfox', label: 'Nightfox' },
      { id: 'rose-pine', label: 'Rose Pine' },
      { id: 'gruvbox', label: 'Gruvbox' },
      { id: 'catppuccin', label: 'Catppuccin' },
      { id: 'solarized', label: 'Solarized Dark' },
    ];
    const storedTheme = localStorage.getItem('envGuiTheme');
    const hour = new Date().getHours();
    const defaultTheme = hour >= 6 && hour < 10 ? 'solarized' : hour >= 10 && hour < 16 ? 'gruvbox' : hour >= 16 && hour < 20 ? 'rose-pine' : 'nightfox';
    const activeTheme = storedTheme || defaultTheme;
    document.documentElement.setAttribute('data-theme', activeTheme);
    themes.forEach(theme => {
      const opt = document.createElement('option');
      opt.value = theme.id;
      opt.textContent = theme.label;
      if (theme.id === activeTheme) opt.selected = true;
      themeSelect.appendChild(opt);
    });
    themeSelect.addEventListener('change', () => {
      const nextTheme = themeSelect.value;
      document.documentElement.setAttribute('data-theme', nextTheme);
      localStorage.setItem('envGuiTheme', nextTheme);
    });
    fields.forEach(field => {
      const wrapper = document.createElement('div');
      const label = document.createElement('label');
      label.textContent = field.key;
      wrapper.appendChild(label);
      let input;
      if (field.type === 'bool') {
        input = document.createElement('select');
        ['true','false'].forEach(val => {
          const opt = document.createElement('option');
          opt.value = val;
          opt.textContent = val;
          if (val === field.value.toLowerCase()) opt.selected = true;
          input.appendChild(opt);
        });
      } else {
        input = document.createElement('input');
        input.type = field.type === 'number' ? 'number' : 'text';
        input.value = field.value;
      }
      input.dataset.key = field.key;
      wrapper.appendChild(input);
      container.appendChild(wrapper);
    });

    document.getElementById('saveBtn').addEventListener('click', async () => {
      status.textContent = 'Saving...';
      const values = {};
      document.querySelectorAll('[data-key]').forEach(input => {
        values[input.dataset.key] = input.value;
      });
      const response = await fetch('/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(values),
      });
      const result = await response.json();
      status.textContent = result.message;
    });
  </script>
</body>
 </html>"""
    return template.replace("__PAYLOAD__", payload_literal)


class EnvGuiHandler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: str, content_type: str = "text/html") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/":
            self._send(HTTPStatus.NOT_FOUND, "Not found", "text/plain")
            return
        entries = _load_entries()
        html = _build_html(entries)
        self._send(HTTPStatus.OK, html)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/save":
            self._send(HTTPStatus.NOT_FOUND, "Not found", "text/plain")
            return
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(content_length).decode("utf-8")
        try:
            updates = json.loads(payload)
        except json.JSONDecodeError:
            self._send(
                HTTPStatus.BAD_REQUEST,
                json.dumps({"message": "Invalid JSON."}),
                "application/json",
            )
            return

        entries = _load_example_entries()
        env_values = _load_env_map(ENV_PATH)
        example_keys = {
            entry["key"] for entry in entries if entry.get("type") == "kv"
        }
        extras = {key: value for key, value in env_values.items() if key not in example_keys}
        _write_entries(entries, updates, extras)
        self._send(
            HTTPStatus.OK,
            json.dumps({"message": "Saved config/.env successfully."}),
            "application/json",
        )


def main() -> None:
    host = "127.0.0.1"
    port = 8765
    server = HTTPServer((host, port), EnvGuiHandler)
    print(f"Env GUI running at http://{host}:{port} (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
