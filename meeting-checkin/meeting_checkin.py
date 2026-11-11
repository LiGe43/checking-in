from __future__ import annotations

import csv
import io
import json
import os
import socket
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


PORT = int(os.environ.get("PORT", os.environ.get("CHECKIN_PORT", "5173")))
DATABASE_URL = os.environ.get("DATABASE_URL")
DATA_FILE = Path(__file__).with_name("checkins.json")
DISPLAY_ZONE = ZoneInfo("Asia/Shanghai")


PAGE = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>会议签到</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
  <style>
    :root { --ink:#17211b; --muted:#66736b; --paper:#f7f4ed; --mint:#b9e8d0; --green:#23734e; --line:#d9ded6; --white:#fffdf8; }
    * { box-sizing:border-box; }
    body { margin:0; color:var(--ink); background:radial-gradient(circle at 8% 8%, #dff4e6 0 16%, transparent 36%), var(--paper); font-family:Georgia, "Microsoft YaHei", serif; }
    main { width:min(1080px, calc(100% - 32px)); margin:0 auto; padding:42px 0 56px; }
    header { display:flex; justify-content:space-between; gap:20px; align-items:end; margin-bottom:28px; }
    .eyebrow { color:var(--green); font:700 12px/1.2 Arial, sans-serif; letter-spacing:2px; text-transform:uppercase; }
    h1 { font-size:clamp(34px, 7vw, 72px); line-height:.95; margin:9px 0 0; font-weight:500; }
    .date { color:var(--muted); font:14px Arial, sans-serif; text-align:right; }
    .layout { display:grid; grid-template-columns: minmax(280px, 390px) 1fr; gap:18px; }
    .panel { background:rgba(255,253,248,.88); border:1px solid var(--line); border-radius:8px; padding:24px; box-shadow:0 12px 30px rgba(31,53,40,.06); }
    .qr-panel { text-align:center; }
    #qrcode { display:grid; place-items:center; min-height:260px; margin:10px auto 18px; }
    #qrcode img { border:12px solid white; box-shadow:0 5px 16px rgba(0,0,0,.1); }
    .url { overflow-wrap:anywhere; color:var(--muted); font:12px/1.5 Arial,sans-serif; }
    .stats { display:flex; gap:26px; border-bottom:1px solid var(--line); padding-bottom:18px; margin-bottom:16px; }
    .stat strong { display:block; font-size:38px; font-weight:500; }
    .stat span { color:var(--muted); font:12px Arial,sans-serif; }
    .toolbar { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:12px; }
    button { border:0; border-radius:4px; background:var(--green); color:white; padding:11px 16px; cursor:pointer; font:700 13px Arial,sans-serif; }
    button.secondary { background:transparent; color:var(--green); border:1px solid var(--green); }
    button.danger { background:transparent; color:#a03c32; border:1px solid #a03c32; }
    table { width:100%; border-collapse:collapse; font:14px Arial,sans-serif; }
    th,td { text-align:left; padding:12px 8px; border-bottom:1px solid var(--line); }
    th { color:var(--muted); font-size:11px; letter-spacing:1px; }
    .form { max-width:460px; margin:11vh auto; }
    .form h1 { font-size:clamp(44px, 12vw, 80px); }
    label { display:block; color:var(--muted); font:13px Arial,sans-serif; margin:28px 0 8px; }
    input { width:100%; border:0; border-bottom:2px solid var(--ink); padding:12px 0; outline:0; background:transparent; font:24px Georgia,serif; }
    .submit { width:100%; margin-top:28px; padding:15px; font-size:15px; }
    .success { text-align:center; }
    .success .mark { color:var(--green); font-size:68px; }
    .empty { color:var(--muted); padding:28px 8px; text-align:center; font:14px Arial,sans-serif; }
    @media (max-width:720px) { main { padding-top:26px; } header { display:block; } .date { text-align:left; margin-top:12px; } .layout { grid-template-columns:1fr; } .panel { padding:18px; } }
  </style>
</head>
<body>
  <main id="app"></main>
  <script>
    const app = document.querySelector('#app');
    const isForm = location.hash === '#form';
    const endpoint = '/api/checkins';
    const nowText = () => new Intl.DateTimeFormat('zh-CN', { dateStyle:'medium', timeStyle:'short' }).format(new Date());

    function renderForm() {
      app.innerHTML = `<section class="panel form"><div class="eyebrow">MEETING CHECK-IN</div><h1>会议签到</h1><p style="color:var(--muted);font:15px Arial,sans-serif">请输入姓名，点击按钮完成签到。</p><form id="form"><label for="name">姓名</label><input id="name" name="name" autocomplete="name" maxlength="40" required autofocus placeholder="请输入您的姓名"><button class="submit" type="submit">签到</button></form></section>`;
      document.querySelector('#form').addEventListener('submit', async (event) => {
        event.preventDefault();
        const button = event.target.querySelector('button');
        const name = document.querySelector('#name').value.trim();
        if (!name) return;
        button.disabled = true; button.textContent = '提交中...';
        const response = await fetch(endpoint, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name}) });
        if (response.ok) renderSuccess(name);
        else { button.disabled = false; button.textContent = '签到'; alert('签到失败，请稍后重试'); }
      });
    }

    function renderSuccess(name) {
      app.innerHTML = `<section class="panel form success"><div class="mark">✓</div><div class="eyebrow">CHECKED IN</div><h1 style="font-size:52px">签到成功</h1><p style="font:18px Arial,sans-serif">${escapeHtml(name)}</p><p style="color:var(--muted);font:14px Arial,sans-serif">${nowText()}</p></section>`;
    }

    async function renderAdmin() {
      app.innerHTML = `<header><div><div class="eyebrow">MEETING CHECK-IN</div><h1>签到管理</h1></div><div class="date">二维码扫码入口<br>${location.host}</div></header><section class="layout"><div class="panel qr-panel"><div class="eyebrow">SCAN TO CHECK IN</div><div id="qrcode"></div><div class="url">请让参会者扫描此二维码。二维码地址：${location.origin}${location.pathname}#form</div></div><div class="panel"><div class="stats"><div class="stat"><strong id="total">0</strong><span>已签到</span></div><div class="stat"><strong id="today">0</strong><span>今日签到</span></div></div><div class="toolbar"><strong>签到名单</strong><div><button class="secondary" id="export">导出 CSV</button> <button class="danger" id="clear">清除</button></div></div><div id="list"></div></div></section>`;
      new QRCode(document.querySelector('#qrcode'), { text: `${location.origin}${location.pathname}#form`, width:230, height:230, colorDark:'#17211b', colorLight:'#ffffff' });
      document.querySelector('#export').addEventListener('click', exportCsv);
      document.querySelector('#clear').addEventListener('click', clearEntries);
      await refresh();
      setInterval(refresh, 3000);
    }

    async function refresh() {
      const entries = await fetch(endpoint).then(r => r.json());
      document.querySelector('#total').textContent = entries.length;
      const today = new Date().toISOString().slice(0,10);
      document.querySelector('#today').textContent = entries.filter(e => e.time.startsWith(today)).length;
      document.querySelector('#list').innerHTML = entries.length ? `<table><thead><tr><th>姓名</th><th>签到时间</th></tr></thead><tbody>${entries.slice().reverse().map(e => `<tr><td>${escapeHtml(e.name)}</td><td>${escapeHtml(e.display_time)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">等待参会者签到</div>';
      window.entries = entries;
    }

    function exportCsv() {
      const rows = [['姓名','签到时间'], ...(window.entries || []).map(e => [e.name, e.display_time])];
      const csv = '\ufeff' + rows.map(row => row.map(value => `"${String(value).replaceAll('"','""')}"`).join(',')).join('\n');
      const link = document.createElement('a'); link.href = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8'})); link.download = '会议签到.csv'; link.click(); URL.revokeObjectURL(link.href);
    }

    async function clearEntries() {
      if (!window.entries?.length || !confirm('确定清除全部签到记录吗？此操作不可撤销。')) return;
      const response = await fetch(endpoint, { method:'DELETE' });
      if (response.ok) await refresh();
      else alert('清除失败，请稍后重试');
    }

    function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
    isForm ? renderForm() : renderAdmin();
  </script>
</body>
</html>'''


def load_entries() -> list[dict[str, str]]:
  if DATABASE_URL:
    import psycopg

    with psycopg.connect(DATABASE_URL) as connection:
      rows = connection.execute(
        "SELECT name, checkin_time, display_time FROM checkins ORDER BY checkin_time"
      ).fetchall()
    return [
      {"name": name, "time": checkin_time.isoformat(), "display_time": display_time}
      for name, checkin_time, display_time in rows
    ]
  if not DATA_FILE.exists():
    return []
  try:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError):
    return []


def save_entries(entries: list[dict[str, str]]) -> None:
    DATA_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def append_entry(entry: dict[str, str]) -> None:
  if DATABASE_URL:
    import psycopg

    with psycopg.connect(DATABASE_URL) as connection:
      connection.execute(
        "INSERT INTO checkins (name, checkin_time, display_time) VALUES (%s, NOW(), %s)",
        (entry["name"], entry["display_time"]),
      )
    return
  entries = load_entries()
  entries.append(entry)
  save_entries(entries)


def clear_entries() -> None:
  if DATABASE_URL:
    import psycopg

    with psycopg.connect(DATABASE_URL) as connection:
      connection.execute("DELETE FROM checkins")
    return
  save_entries([])


def ensure_database() -> None:
  if not DATABASE_URL:
    return
  import psycopg

  with psycopg.connect(DATABASE_URL) as connection:
    connection.execute(
      """
      CREATE TABLE IF NOT EXISTS checkins (
        id BIGSERIAL PRIMARY KEY,
        name VARCHAR(40) NOT NULL,
        checkin_time TIMESTAMPTZ NOT NULL,
        display_time VARCHAR(32) NOT NULL
      )
      """
    )


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, data: object) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/checkins":
            self.send_json(200, load_entries())
            return
        payload = PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/checkins":
            self.send_json(404, {"error": "not found"})
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            name = str(body.get("name", "")).strip()[:40]
        except (json.JSONDecodeError, ValueError):
            name = ""
        if not name:
            self.send_json(400, {"error": "name is required"})
            return
        current = datetime.now(DISPLAY_ZONE)
        entry = {"name": name, "time": current.isoformat(), "display_time": current.strftime("%Y-%m-%d %H:%M:%S")}
        try:
          append_entry(entry)
        except Exception as error:
          print(f"签到写入失败: {error}")
          self.send_json(500, {"error": "database write failed"})
          return
        self.send_json(201, entry)

    def do_DELETE(self) -> None:
        if urlparse(self.path).path != "/api/checkins":
            self.send_json(404, {"error": "not found"})
            return
        try:
            clear_entries()
        except Exception as error:
            print(f"清除签到失败: {error}")
            self.send_json(500, {"error": "database delete failed"})
            return
        self.send_json(200, {"cleared": True})

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{datetime.now():%H:%M:%S}] {format % args}")


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


if __name__ == "__main__":
    ensure_database()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"组织者页面: http://localhost:{PORT}/")
    print(f"手机扫码地址: http://{local_ip()}:{PORT}/#form")
    print("按 Ctrl+C 停止服务")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        server.server_close()