"""데스크탑 운영 도우미: 파일럿 기간 동안 내 컴퓨터를 서버로 쓸 때 필요한 일을 한 명령으로 묶는다.

    python -m etfrec desktop            # 윈도우는 deploy/desktop/start-windows.bat, 맥은 start-mac.command를 더블클릭

1. 첫 실행 준비: 번들이 없으면 학습, 운영 등록부 생성, 관리자 계정이 없으면 입력받아 만든다.
2. 서버와 공개 주소를 함께 띄운다.
   - 고정 주소(무료): Tailscale Funnel(tailscale funnel --bg 8000을 한 번 실행해 두면 https://이름.tailnet.ts.net)
   - 고정 주소(내 도메인): Cloudflare 터널 토큰(환경변수 ETFREC_TUNNEL_TOKEN 또는 runs/desktop/tunnel_token.txt)
   - 임시 주소: 둘 다 없으면 trycloudflare.com 주소를 받는다. 다시 켤 때마다 주소가 바뀐다(리허설용).
   - 같은 와이파이: cloudflared도 Funnel도 없거나 --tunnel none이면 같은 망에서만 접속(HTTP)
   - 초대 코드(환경변수 ETFREC_INVITE_CODE 또는 runs/desktop/invite_code.txt)가 있으면 그 코드를 아는 사람만 가입한다.
3. 서버나 터널이 죽거나 상태 확인(/api/health)이 3번 연속 실패하면 다시 켠다.
4. 켜져 있는 동안 컴퓨터가 절전으로 들어가지 않게 한다(윈도우·맥).
5. 시작할 때와 매일 정한 시각에 계정·기록 DB를 백업하고 최근 N개만 남긴다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime

QUICK_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
HEALTH_EVERY = 60          # 초
HEALTH_FAILS = 3           # 연속 실패 횟수 → 서버 재시작


def _setting(desktop_dir: str, env_name: str, file_name: str):
    """환경변수가 있으면 그 값, 없으면 runs/desktop/<file_name>의 내용(앞뒤 공백 제거). 명령줄 인자로는 받지 않는다."""
    val = os.environ.get(env_name, "").strip()
    path = os.path.join(desktop_dir, file_name)
    if not val and os.path.exists(path):
        try:
            with open(path, encoding="utf-8-sig") as f:                  # 메모장이 붙이는 BOM을 떼어 낸다
                val = f.read().strip()
        except UnicodeDecodeError:
            raise ValueError(f"{path}를 UTF-8로 읽지 못했습니다. 영문·숫자로 다시 적거나 메모장에서 UTF-8로 저장하세요") from None
    return val or None


def tunnel_token(desktop_dir: str):
    """고정 주소 터널 토큰: 환경변수 ETFREC_TUNNEL_TOKEN 또는 runs/desktop/tunnel_token.txt."""
    return _setting(desktop_dir, "ETFREC_TUNNEL_TOKEN", "tunnel_token.txt")


def invite_code(desktop_dir: str):
    """가입 초대 코드: 환경변수 ETFREC_INVITE_CODE 또는 runs/desktop/invite_code.txt. 없으면 누구나 가입한다."""
    code = _setting(desktop_dir, "ETFREC_INVITE_CODE", "invite_code.txt")
    if code and len(code) > 64:
        raise ValueError("초대 코드는 64자 이하로 정해 주세요(가입 화면의 입력 한도)")
    return code


WINDOWS_CLOUDFLARED = (r"C:\Program Files (x86)\cloudflared\cloudflared.exe", r"C:\Program Files\cloudflared\cloudflared.exe")
TAILSCALE_PATHS = {"win32": (r"C:\Program Files\Tailscale\tailscale.exe",),
                   "darwin": ("/Applications/Tailscale.app/Contents/MacOS/Tailscale",)}


def _find_exe(name: str, explicit: str, fallback) -> str:
    if explicit:
        if not os.path.isfile(explicit):
            raise ValueError(f"{name} 경로가 없습니다: {explicit}")
        return explicit
    found = shutil.which(name)
    if found:
        return found
    for path in fallback:
        if os.path.isfile(path):
            return path
    return None


def find_cloudflared(explicit: str = None):
    """cloudflared 실행 파일: 지정한 경로 → PATH → 윈도우 기본 설치 위치(winget 설치 직후 PATH가 아직 반영되지 않은 창 대비)."""
    return _find_exe("cloudflared", explicit, WINDOWS_CLOUDFLARED if sys.platform == "win32" else ())


def find_tailscale(explicit: str = None):
    """tailscale 명령: 지정한 경로 → PATH → 기본 설치 위치(윈도우 Program Files, 맥 앱)."""
    return _find_exe("tailscale", explicit, TAILSCALE_PATHS.get(sys.platform, ()))


def funnel_address(serve_config, port: int):
    """`tailscale serve status --json`(Tailscale의 serve 설정)에서 이 컴퓨터의 port로 이어지는 Funnel 공개 주소. 없으면 None."""
    configs = [serve_config or {}]
    configs += [c for c in ((serve_config or {}).get("Foreground") or {}).values() if c]      # 다른 창에서 켜 둔 tailscale funnel
    for c in configs:
        allowed = c.get("AllowFunnel") or {}
        for hostport, web in (c.get("Web") or {}).items():
            if not allowed.get(hostport):
                continue
            for handler in ((web or {}).get("Handlers") or {}).values():
                target = urllib.parse.urlsplit((handler or {}).get("Proxy") or "")
                if target.hostname in ("127.0.0.1", "localhost", "::1") and target.port == int(port):
                    host, _, public_port = hostport.rpartition(":")
                    return f"https://{host}" + ("" if public_port == "443" else f":{public_port}")
    return None


def tailscale_funnel(tailscale, port: int):
    """Funnel이 이 포트로 켜져 있으면 고정 공개 주소. Tailscale은 윈도우 서비스·맥 앱으로 따로 돌아 실행 도우미가 켜고 끄지 않는다."""
    if not tailscale:
        return None
    try:
        out = subprocess.run([tailscale, "serve", "status", "--json"], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=15)
        return funnel_address(json.loads(out.stdout or "null"), port)
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        return None


def tunnel_mode(requested: str, token, cloudflared, funnel=None) -> str:
    """auto: Cloudflare 토큰이 있으면 그 고정 주소, Tailscale Funnel이 켜져 있으면 그 고정 주소, 아니면 임시 주소,
    cloudflared도 Funnel도 없으면 같은 와이파이. tailscale은 Funnel을 확인하지 못해도 그대로 둔다(Tailscale이 늦게 켜진 경우)."""
    if requested == "auto":
        if cloudflared and token:
            return "token"
        if funnel:
            return "tailscale"
        return "quick" if cloudflared else "none"
    if requested in ("token", "quick") and not cloudflared:
        raise ValueError("cloudflared가 설치되어 있지 않습니다(윈도우: winget install --id Cloudflare.cloudflared, 맥: brew install cloudflared)")
    if requested == "token" and not token:
        raise ValueError("터널 토큰이 없습니다. runs/desktop/tunnel_token.txt에 붙여 넣거나 환경변수 ETFREC_TUNNEL_TOKEN으로 주세요")
    return requested


def server_command(python: str, port: int, mode: str, db: str, ops_dir: str, bundle: str, designs: str) -> list:
    cmd = [python, "-m", "etfrec", "serve", "--public", "--port", str(port), "--db", db, "--designs", designs]
    cmd += ["--ops-dir", ops_dir] if ops_dir else ["--bundle", bundle]
    if mode == "none":
        return cmd + ["--host", "0.0.0.0", "--cookies", "insecure"]      # 같은 와이파이 시험(HTTP라 Secure 쿠키를 쓸 수 없다)
    return cmd + ["--host", "127.0.0.1", "--trust-proxy"]                 # 터널(HTTPS) 뒤: 외부에서는 터널로만 들어온다


def tunnel_command(cloudflared: str, mode: str, port: int):
    """(명령, 추가 환경변수). 토큰은 프로세스 목록에 보이지 않게 환경변수 TUNNEL_TOKEN으로 넘긴다."""
    if mode == "token":
        return [cloudflared, "tunnel", "--no-autoupdate", "run"], {"TUNNEL_TOKEN": None}
    if mode == "quick":
        return [cloudflared, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"], {}
    return None, {}


def backup_due(now: datetime, last_day, hour: int) -> bool:
    return now.hour >= hour and last_day != now.date()


def prune_backups(folder: str, keep: int) -> list:
    """etfrec-*.db 가운데 최근 keep개만 남기고 지운다. 지운 파일 목록."""
    if not os.path.isdir(folder):
        return []
    files = sorted(f for f in os.listdir(folder) if f.startswith("etfrec-") and f.endswith(".db"))
    gone = files[:-keep] if keep > 0 else files
    for f in gone:
        os.remove(os.path.join(folder, f))
    return gone


def lan_addresses() -> list:
    out = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))                                  # 패킷을 보내지 않고 바깥쪽 인터페이스 주소만 얻는다
        out.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(a for a in out if not a.startswith("127."))


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, int(port))) == 0


def graceful_signals():
    """종료 신호(SIGTERM, 윈도우 SIGBREAK)도 Ctrl+C처럼 처리해 서버·터널을 함께 끈다."""
    import signal

    def handler(signum, frame):
        raise KeyboardInterrupt
    for name in ("SIGTERM", "SIGBREAK", "SIGHUP"):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), handler)
            except (ValueError, OSError):                                     # 메인 스레드가 아니거나 지원하지 않는 환경
                pass


def prevent_sleep(log):
    """켜져 있는 동안 절전(유휴 잠자기)을 막는다. 덮개를 닫거나 전원을 끄는 것까지 막지는 못한다."""
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
            log("절전 방지 켬(이 창이 열려 있는 동안)")
        elif sys.platform == "darwin" and shutil.which("caffeinate"):
            subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
            log("절전 방지 켬(caffeinate, 이 창이 열려 있는 동안)")
    except Exception as e:                                                 # 절전 방지는 실패해도 서버는 계속 돈다
        log(f"절전 방지를 켜지 못했습니다: {e}")


class Proc:
    """하위 프로세스 하나: 출력은 로그 파일에 쌓고, 줄마다 on_line을 부른다."""

    def __init__(self, name: str, cmd: list, log_path: str, env: dict = None, on_line=None, subject: str = None):
        self.name, self.cmd, self.log_path, self.env, self.on_line = name, cmd, log_path, env, on_line
        self.subject = subject or name                                       # 로그 문장의 주어(예: '서버가')
        self.p, self.restarts, self.started_at = None, 0, None

    def start(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONUTF8="1", **(self.env or {}))      # 윈도우에서도 한글 로그가 깨지지 않게
        self.p = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                  errors="replace", bufsize=1, env=env)
        self.started_at = time.time()
        threading.Thread(target=self._pump, args=(self.p,), daemon=True).start()

    def _pump(self, p):
        with open(self.log_path, "a", encoding="utf-8") as f:
            for line in p.stdout:
                f.write(line); f.flush()
                if self.on_line:
                    self.on_line(line)

    def alive(self) -> bool:
        return self.p is not None and self.p.poll() is None

    def stop(self, timeout: float = 10):
        if self.alive():
            self.p.terminate()
            try:
                self.p.wait(timeout)
            except subprocess.TimeoutExpired:
                self.p.kill()


class Supervisor:
    """서버·터널을 지켜보다 죽으면 다시 켜고, 상태 확인 실패가 이어지면 서버를 재시작하고, 정한 시각에 백업한다."""

    def __init__(self, server: Proc, tunnel: Proc = None, health_url: str = None, backup=None, backup_hour: int = 4,
                 restart_delay: float = 5, log=print):
        self.server, self.tunnel, self.health_url = server, tunnel, health_url
        self.backup, self.backup_hour, self.restart_delay, self.log = backup, backup_hour, restart_delay, log
        self.fails, self.last_health, self.last_backup_day = 0, 0.0, None

    def procs(self):
        return [p for p in (self.server, self.tunnel) if p is not None]

    def start(self):
        for p in self.procs():
            p.start()
        if self.backup:
            self._backup("시작")
            now = datetime.now()
            if now.hour >= self.backup_hour:                                  # 정한 시각이 지났으면 시작 백업을 그날 백업으로 친다
                self.last_backup_day = now.date()

    def healthy(self) -> bool:
        try:
            with urllib.request.urlopen(self.health_url, timeout=10) as r:
                return r.status == 200
        except Exception:
            return False

    def _backup(self, why: str):
        try:
            path = self.backup()
            if path:
                self.log(f"백업({why}): {path}")
        except Exception as e:
            self.log(f"백업 실패({why}): {e}")

    def step(self, now: float = None):
        now = time.time() if now is None else now
        for p in self.procs():
            if not p.alive():
                code = p.p.returncode if p.p is not None else None
                self.log(f"{p.subject} 멈췄습니다(종료 코드 {code}). {self.restart_delay:.0f}초 뒤 다시 켭니다")
                time.sleep(self.restart_delay)
                p.start(); p.restarts += 1
                if p is self.server:
                    self.fails, self.last_health = 0, now                     # 막 켠 서버는 준비 시간을 준다
        if self.health_url and self.server.alive() and now - self.last_health >= HEALTH_EVERY \
                and now - (self.server.started_at or 0) >= HEALTH_EVERY:
            self.last_health = now
            if self.healthy():
                self.fails = 0
            else:
                self.fails += 1
                self.log(f"상태 확인 실패 {self.fails}/{HEALTH_FAILS}")
                if self.fails >= HEALTH_FAILS:
                    self.log("서버가 응답하지 않아 다시 켭니다")
                    self.server.stop(); self.server.start(); self.server.restarts += 1; self.fails = 0
        dt = datetime.fromtimestamp(now)
        if self.backup and backup_due(dt, self.last_backup_day, self.backup_hour):
            self.last_backup_day = dt.date()
            self._backup("매일")

    def stop(self):
        for p in self.procs():
            p.stop()


def run_desktop(a, store_factory, bootstrap) -> int:
    """cli의 desktop 명령 본체. store_factory(db) → WebStore, bootstrap(a, store) → 첫 실행 준비."""
    desktop_dir = os.path.join(os.path.dirname(os.path.abspath(a.db)), "..", "desktop") if a.desktop_dir is None else a.desktop_dir
    desktop_dir = os.path.normpath(desktop_dir)
    os.makedirs(desktop_dir, exist_ok=True)
    event_log = os.path.join(desktop_dir, "desktop.log")

    def log(msg):
        line = f"[{datetime.now().strftime('%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        with open(event_log, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    store = store_factory(a.db)
    bootstrap(a, store)
    cloudflared = find_cloudflared(getattr(a, "cloudflared", None) or os.environ.get("ETFREC_CLOUDFLARED") or None)
    token = tunnel_token(desktop_dir)
    funnel = None
    if a.tunnel == "tailscale" or (a.tunnel == "auto" and not (cloudflared and token)):
        funnel = tailscale_funnel(find_tailscale(getattr(a, "tailscale", None) or os.environ.get("ETFREC_TAILSCALE") or None), a.port)
    mode = tunnel_mode(a.tunnel, token, cloudflared, funnel)
    if port_in_use(a.port):
        raise ValueError(f"포트 {a.port}을(를) 이미 다른 프로그램이 쓰고 있습니다. 이전에 켠 서버가 남아 있으면 끄고(작업 관리자·활동 모니터에서 python) "
                         "다시 실행하거나 --port로 다른 번호를 주세요")
    code = invite_code(desktop_dir)
    server = Proc("서버", server_command(sys.executable, a.port, mode, a.db, a.ops_dir, a.bundle, a.designs),
                  os.path.join(desktop_dir, "server.log"), env={"ETFREC_INVITE_CODE": code} if code else None, subject="서버가")
    address_file = os.path.join(desktop_dir, "address.txt")
    if os.path.exists(address_file):
        os.remove(address_file)                                           # 지난번 임시 주소가 남아 헷갈리지 않게
    if funnel and mode == "tailscale":
        with open(address_file, "w", encoding="utf-8") as f:
            f.write(funnel + "\n")

    def on_tunnel_line(line):
        m = QUICK_URL_RE.search(line)
        if m:
            with open(address_file, "w", encoding="utf-8") as f:
                f.write(m.group(0) + "\n")
            log(f"접속 주소(임시, 다시 켜면 바뀜): {m.group(0)}")

    tunnel = None
    cmd, extra = tunnel_command(cloudflared, mode, a.port)
    if cmd:
        env = {k: (token if v is None else v) for k, v in extra.items()}
        tunnel = Proc("터널", cmd, os.path.join(desktop_dir, "tunnel.log"), env=env, on_line=on_tunnel_line if mode == "quick" else None,
                      subject="터널이")

    def backup():
        if not os.path.exists(a.db):
            return None
        os.makedirs(a.backup_dir, exist_ok=True)
        path = os.path.join(a.backup_dir, f"etfrec-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.db")
        store_factory(a.db).backup(path)
        prune_backups(a.backup_dir, a.keep_backups)
        return path

    sup = Supervisor(server, tunnel, health_url=f"http://127.0.0.1:{a.port}/api/health", backup=backup, backup_hour=a.backup_hour,
                     log=log)
    prevent_sleep(log)
    log({"token": "고정 주소 터널(토큰)로 공개합니다. 주소는 Cloudflare에서 정한 도메인입니다",
         "quick": "임시 주소 터널로 공개합니다. 주소는 잠시 뒤 표시됩니다(다시 켜면 바뀌므로 리허설용)",
         "tailscale": f"Tailscale Funnel 고정 주소로 공개합니다: {funnel}" if funnel else
                      f"Tailscale Funnel로 공개합니다. 설정을 확인하지 못했으니 명령 창에서 'tailscale funnel status'로 확인하고, "
                      f"꺼져 있으면 'tailscale funnel --bg {a.port}'를 실행하세요",
         "none": "터널 없이 같은 와이파이에서만 접속합니다: " + ", ".join(f"http://{ip}:{a.port}" for ip in lan_addresses() or ["이 컴퓨터의 IP"])}[mode])
    log(f"가입: 초대 코드 '{code}'가 있어야 합니다" if code else
        f"가입: 누구나 할 수 있습니다. 참가자만 받으려면 {os.path.join(desktop_dir, 'invite_code.txt')}에 초대 코드를 적고 다시 켜세요")
    log(f"관리자 메뉴: 접속 주소 뒤에 /?admin=1 · 로그 폴더 {desktop_dir} · 백업 폴더 {a.backup_dir}(매일 {a.backup_hour}시, 최근 {a.keep_backups}개)")
    log("끄려면 이 창에서 Ctrl+C")
    graceful_signals()
    sup.start()
    try:
        while True:
            sup.step()
            time.sleep(2)
    except KeyboardInterrupt:
        log("끄는 중…")
    finally:
        sup.stop()
    return 0
