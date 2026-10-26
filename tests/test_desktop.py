"""데스크탑 운영 도우미: 터널 방식 고르기, 서버·터널 명령, 백업 시각·보관, 프로세스 자동 재시작."""
import os
import sys
import time
from datetime import datetime

import pytest

from etfrec.desktop import (QUICK_URL_RE, Proc, Supervisor, backup_due, find_cloudflared, invite_code, prune_backups, server_command,
                            tunnel_command, tunnel_mode, tunnel_token)


def test_tunnel_mode_and_commands(tmp_path, monkeypatch):
    assert tunnel_mode("auto", "tok", "/bin/cloudflared") == "token" and tunnel_mode("auto", None, "/bin/cloudflared") == "quick"
    assert tunnel_mode("auto", "tok", None) == "none" and tunnel_mode("none", "tok", "/bin/cloudflared") == "none"
    with pytest.raises(ValueError, match="cloudflared"):
        tunnel_mode("quick", None, None)
    with pytest.raises(ValueError, match="토큰"):
        tunnel_mode("token", None, "/bin/cloudflared")
    s = server_command("py", 8000, "token", "db", "ops", "bundle", "designs")
    assert s[:5] == ["py", "-m", "etfrec", "serve", "--public"] and "--trust-proxy" in s and s[s.index("--host") + 1] == "127.0.0.1"
    lan = server_command("py", 8000, "none", "db", "", "bundle", "designs")
    assert lan[lan.index("--host") + 1] == "0.0.0.0" and lan[lan.index("--cookies") + 1] == "insecure" and "--bundle" in lan
    cmd, env = tunnel_command("cf", "token", 8000)
    assert cmd == ["cf", "tunnel", "--no-autoupdate", "run"] and "TUNNEL_TOKEN" in env    # 토큰은 명령줄이 아니라 환경변수로
    cmd, env = tunnel_command("cf", "quick", 8123)
    assert cmd[-1] == "http://127.0.0.1:8123" and env == {} and tunnel_command("cf", "none", 1) == (None, {})
    monkeypatch.delenv("ETFREC_TUNNEL_TOKEN", raising=False)
    assert tunnel_token(str(tmp_path)) is None
    (tmp_path / "tunnel_token.txt").write_text(" abc123 \n", encoding="utf-8")
    assert tunnel_token(str(tmp_path)) == "abc123"
    monkeypatch.setenv("ETFREC_TUNNEL_TOKEN", "envtok")
    assert tunnel_token(str(tmp_path)) == "envtok"
    line = "2026-11-02T00:00:00Z INF |  https://gentle-river-1234.trycloudflare.com                    |"
    assert QUICK_URL_RE.search(line).group(0) == "https://gentle-river-1234.trycloudflare.com"


def test_invite_code(tmp_path, monkeypatch):
    monkeypatch.delenv("ETFREC_INVITE_CODE", raising=False)
    assert invite_code(str(tmp_path)) is None
    (tmp_path / "invite_code.txt").write_bytes("﻿etf2026 \r\n".encode("utf-8"))     # 메모장 저장: BOM과 CRLF
    assert invite_code(str(tmp_path)) == "etf2026"
    (tmp_path / "invite_code.txt").write_bytes("수업".encode("cp949"))                   # 명령 창 echo로 만든 한글(UTF-8 아님)
    with pytest.raises(ValueError, match="UTF-8"):
        invite_code(str(tmp_path))
    monkeypatch.setenv("ETFREC_INVITE_CODE", "envcode")
    assert invite_code(str(tmp_path)) == "envcode"
    monkeypatch.setenv("ETFREC_INVITE_CODE", "x" * 65)
    with pytest.raises(ValueError, match="64자"):
        invite_code(str(tmp_path))


def test_find_cloudflared(tmp_path, monkeypatch):
    exe = tmp_path / "cloudflared"
    exe.write_text("", encoding="utf-8")
    assert find_cloudflared(str(exe)) == str(exe)                                 # 지정한 경로가 먼저
    with pytest.raises(ValueError, match="경로가 없습니다"):
        find_cloudflared(str(tmp_path / "없음"))
    monkeypatch.setenv("PATH", str(tmp_path / "빈 폴더"))
    assert find_cloudflared() is None                                              # PATH에도 기본 위치에도 없으면 None(같은 와이파이 방식)


def test_port_check(tmp_path):
    import socket
    from etfrec.desktop import port_in_use
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0)); srv.listen(1)
        port = srv.getsockname()[1]
        assert port_in_use(port)
    assert not port_in_use(port)


def test_backup_schedule_and_rotation(tmp_path):
    d = datetime(2026, 11, 10, 3, 59)
    assert not backup_due(d, None, 4) and backup_due(d.replace(hour=4), None, 4)
    assert not backup_due(d.replace(hour=5), d.date(), 4) and backup_due(d.replace(day=11, hour=4), d.date(), 4)
    for day in range(1, 8):
        (tmp_path / f"etfrec-202611{day:02d}-040000.db").write_bytes(b"x")
    (tmp_path / "other.txt").write_text("keep", encoding="utf-8")
    gone = prune_backups(str(tmp_path), 3)
    assert len(gone) == 4 and sorted(os.listdir(tmp_path)) == ["etfrec-20261105-040000.db", "etfrec-20261106-040000.db",
                                                             "etfrec-20261107-040000.db", "other.txt"]


def test_supervisor_restarts_a_stopped_process_and_runs_daily_backup(tmp_path):
    logs, backups = [], []
    quick_exit = Proc("서버", [sys.executable, "-c", "print('안녕')"], str(tmp_path / "server.log"), subject="서버가")
    sup = Supervisor(quick_exit, backup=lambda: backups.append(1) or "b.db", backup_hour=0, restart_delay=0, log=logs.append)
    sup.start()
    assert backups == [1]                                                         # 시작할 때 한 번 백업(0시 이후라 그날 백업으로 친다)
    quick_exit.p.wait(10)
    sup.step()
    assert quick_exit.restarts == 1 and any(m.startswith("서버가 멈췄습니다") for m in logs)
    assert backups == [1]                                                         # 같은 날 다시 하지 않는다
    sup.step(now=time.time() + 86400)
    quick_exit.p.wait(10)
    assert backups == [1, 1]                                                      # 다음 날 정한 시각이 지나면 한 번
    sup.stop()
    time.sleep(0.2)
    assert "안녕" in (tmp_path / "server.log").read_text(encoding="utf-8")       # 출력은 로그 파일로
