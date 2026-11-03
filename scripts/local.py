#!/usr/bin/env python3
"""Manage native app processes; Docker supplies only PostgreSQL, Redis and Docs."""

import argparse
import fcntl
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".local" / "run"
PYTHON = ROOT / "backend" / ".venv" / "bin" / "python"
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    str(ROOT / ".env"),
    "-f",
    str(ROOT / "deploy/compose.yaml"),
]
SERVICES = ("api", "worker", "scheduler", "web")
PORTS = {"api": 18400, "web": 15173}


def run(command, **kwargs):
    kwargs.setdefault("cwd", ROOT)
    return subprocess.run(command, check=True, **kwargs)


def process_identity(pid):
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "stat=", "-o", "lstart="],
        check=False,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    return value if value and not value.startswith("Z") else None


def state(name):
    path = RUNTIME / f"{name}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    current = process_identity(data["pid"])
    # Compare creation time, not process state (R/S changes while running).
    try:
        if (
            current
            and current.split(maxsplit=1)[1] == data["started"]
            and os.getpgid(data["pid"]) == data["pid"]
        ):
            return data
    except ProcessLookupError:
        pass
    path.unlink(missing_ok=True)
    return None


def commands():
    return {
        "api": [
            str(PYTHON),
            "-m",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--reload-dir",
            "app",
            "--host",
            "127.0.0.1",
            "--port",
            "18400",
        ],
        "worker": [
            str(PYTHON),
            "-m",
            "celery",
            "-A",
            "app.worker:celery_app",
            "worker",
            "--loglevel=INFO",
            "--pool=solo",
            "--concurrency=1",
            "--hostname=contract-native@%h",
        ],
        "scheduler": [
            str(PYTHON),
            "-m",
            "celery",
            "-A",
            "app.worker:celery_app",
            "beat",
            "--loglevel=INFO",
            f"--schedule={RUNTIME / 'celerybeat-schedule'}",
        ],
        "web": [shutil.which("pnpm") or "pnpm", "dev"],
    }


def stop(name):
    data = state(name)
    if not data:
        return
    try:
        os.killpg(data["pid"], signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 150
    while state(name):
        if time.monotonic() >= deadline:
            raise RuntimeError(f"{name} 正在等待任务结束，未强制终止；请查看日志。")
        time.sleep(0.2)
    print(f"{name}: stopped", flush=True)


def start(name, command):
    if state(name):
        return False
    port = PORTS.get(name)
    if port:
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(
                    f"端口 {port} 已被其他进程占用；不会终止未托管的进程。"
                )
    env = dict(
        os.environ, PYTHONUNBUFFERED="1", API_PROXY_TARGET="http://127.0.0.1:18400"
    )
    with (RUNTIME / f"{name}.log").open("ab") as output:
        process = subprocess.Popen(
            command,
            cwd=ROOT / ("frontend" if name == "web" else "backend"),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    identity = process_identity(process.pid)
    if not identity:
        raise RuntimeError(f"{name} 启动失败，查看 {RUNTIME / (name + '.log')}")
    (RUNTIME / f"{name}.json").write_text(
        json.dumps(
            {
                "pid": process.pid,
                "started": identity.split(maxsplit=1)[1],
            }
        )
    )
    print(f"{name}: started PID {process.pid}", flush=True)
    return True


def wait_http(name, url):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if not state(name):
            break
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.3)
    raise RuntimeError(f"{name} 未就绪，查看 {RUNTIME / (name + '.log')}")


def wait_worker():
    probe = (
        "from app.worker import celery_app; "
        "replies=celery_app.control.inspect(timeout=1).ping() or {}; "
        "raise SystemExit(0 if any(k.startswith('contract-native@') for k in replies) else 1)"
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and state("worker"):
        result = subprocess.run(
            [str(PYTHON), "-c", probe],
            check=False,
            cwd=ROOT / "backend",
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return
        time.sleep(0.5)
    raise RuntimeError(f"worker 未响应队列检查，查看 {RUNTIME / 'worker.log'}")


def up():
    if not (ROOT / ".env").exists():
        raise RuntimeError(
            "请先由 .env.example 创建 .env，并配置 ONLYOFFICE_JWT_SECRET。"
        )
    if not PYTHON.exists() or not (ROOT / "frontend/node_modules").is_dir():
        raise RuntimeError("请先执行 make install 安装本机依赖。")
    running = run(
        [
            *COMPOSE,
            "--profile",
            "application",
            "ps",
            "--services",
            "--status",
            "running",
        ],
        capture_output=True,
        text=True,
    ).stdout.split()
    conflicts = set(running) & {
        "api",
        "worker",
        "scheduler",
        "frontend",
        "migrate",
        "gateway",
    }
    if conflicts:
        raise RuntimeError(
            f"仍有容器应用在运行：{', '.join(sorted(conflicts))}；请先完成数据迁移并停止它们。"
        )
    run([*COMPOSE, "up", "-d", "--wait", "postgres", "redis", "onlyoffice"])
    # Use the same settings and absolute preview directory as all native services.
    run([str(PYTHON), "-m", "alembic", "upgrade", "head"], cwd=ROOT / "backend")
    started = []
    try:
        for name, command in commands().items():
            if start(name, command):
                started.append(name)
        wait_http("api", "http://127.0.0.1:18400/api/v1/health/live")
        wait_http("web", "http://127.0.0.1:15173/")
        if "worker" in started:
            wait_worker()
        for name in SERVICES:
            if not state(name):
                raise RuntimeError(f"{name} 已退出，请查看日志。")
    except Exception:
        for name in reversed(started):
            stop(name)
        raise
    print(
        "本地应用已启动：http://127.0.0.1:15173\n日志目录：" + str(RUNTIME), flush=True
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["up", "stop", "restart", "status"])
    action = parser.parse_args().action
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / "manager.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if action in {"stop", "restart"}:
            for name in ("web", "scheduler", "worker", "api"):
                stop(name)
        if action in {"up", "restart"}:
            up()
        if action == "status":
            for name in SERVICES:
                data = state(name)
                print(
                    f"{name}: " + (f"running PID {data['pid']}" if data else "stopped"),
                    flush=True,
                )
            run([*COMPOSE, "ps"])


if __name__ == "__main__":
    try:
        main()
    except (
        RuntimeError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        OSError,
    ) as error:
        print(f"启动管理失败：{error}", file=sys.stderr)
        sys.exit(1)
