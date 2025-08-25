#!/usr/bin/env python3
import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
from aiohttp import web


ENV_PATH = "/etc/vpn-agent/agent.env"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[agent] {ts} {msg}")
    sys.stdout.flush()


def load_env(path: str) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


async def run_cmd(cmd: List[str], timeout: int = 10) -> Tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return 1, "", "timeout"
        return proc.returncode, stdout.decode(), stderr.decode()
    except Exception as e:
        return 1, "", str(e)


async def default_iface() -> str:
    rc, out, _ = await run_cmd(["ip", "route", "get", "1.1.1.1"])  # iproute2
    if rc == 0:
        m = re.search(r" dev (\S+)", out)
        if m:
            return m.group(1)
    return ""


def read_proc(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def read_dev_counters(iface: str) -> Tuple[int, int, int, int, int, int, int, int]:
    # returns rx_bytes, rx_packets, rx_errs, rx_drop, tx_bytes, tx_packets, tx_errs, tx_drop
    data = read_proc("/proc/net/dev").splitlines()
    for line in data[2:]:
        parts = re.split(r"[:\s]+", line.strip())
        if not parts:
            continue
        if parts[0] == iface:
            nums = list(map(int, parts[1:]))
            # rx: bytes, packets, errs, drop, fifo, frame, compressed, multicast
            # tx: bytes, packets, errs, drop, fifo, colls, carrier, compressed
            return nums[0], nums[1], nums[2], nums[3], nums[8], nums[9], nums[10], nums[11]
    return 0, 0, 0, 0, 0, 0, 0, 0


async def cpu_sample() -> Tuple[float, float]:
    # returns cpu_total_pct, softirq_pct
    def read_cpu():
        line = read_proc("/proc/stat").splitlines()[0]
        fields = list(map(int, line.split()[1:]))
        # user, nice, system, idle, iowait, irq, softirq, steal
        return fields

    a = read_cpu()
    await asyncio.sleep(0.2)
    b = read_cpu()
    idle_a = a[3] + a[4]
    idle_b = b[3] + b[4]
    total_a = sum(a)
    total_b = sum(b)
    total = max(1, total_b - total_a)
    busy = (total - (idle_b - idle_a))
    softirq_delta = b[6] - a[6]
    cpu_pct = round(busy * 100.0 / total, 1)
    softirq_pct = round(softirq_delta * 100.0 / total, 1)
    return cpu_pct, softirq_pct


def tcp_ext_value(key: str) -> int:
    # Parse /proc/net/netstat pairs for TcpExt
    data = read_proc("/proc/net/netstat").splitlines()
    for i in range(0, len(data) - 1, 2):
        if data[i].startswith("TcpExt:") and data[i + 1].startswith("TcpExt:"):
            headers = data[i].split()[1:]
            values = data[i + 1].split()[1:]
            if key in headers:
                idx = headers.index(key)
                try:
                    return int(values[idx])
                except Exception:
                    return 0
    return 0


async def measure_ping(target: str = "1.1.1.1", count: int = 8, deadline: int = 5) -> Tuple[float, float, float]:
    # returns (p50_ms, p95_ms, loss_pct)
    rc, out, _ = await run_cmd(["ping", "-n", "-q", "-w", str(deadline), "-c", str(count), target], timeout=deadline + 2)
    if rc != 0:
        return 0.0, 0.0, 100.0
    loss_pct = 100.0
    m = re.search(r"(\d+\.?\d*)% packet loss", out)
    if m:
        loss_pct = float(m.group(1))

    times: List[float] = []
    for line in out.splitlines():
        m2 = re.search(r"time=(\d+\.?\d*) ms", line)
        if m2:
            times.append(float(m2.group(1)))
    if not times:
        return 0.0, 0.0, loss_pct
    times.sort()
    def pct(p: float) -> float:
        if not times:
            return 0.0
        idx = int(round((len(times) - 1) * p))
        return times[min(max(idx, 0), len(times) - 1)]
    return pct(0.5), pct(0.95), loss_pct


async def http_post_json(url: str, token: str, payload: Dict[str, Any]) -> None:
    import aiohttp
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=headers, timeout=10) as _:
                await _.read()
        except Exception:
            pass


async def http_get_json(url: str, token: str) -> Any:
    import aiohttp
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as resp:
                return await resp.json(content_type=None)
        except Exception:
            return []


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(path: str, data: Any) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def apply_tasks(tasks: List[Dict[str, Any]], xray_config_path: str) -> None:
    try:
        cfg = read_json(xray_config_path)
    except Exception:
        return
    changed = False
    inbounds = cfg.get("inbounds", [])
    vless_inbounds = [b for b in inbounds if b.get("protocol") == "vless"]
    for task in tasks:
        action = str(task.get("type", "")).strip()
        user_id = str(task.get("id", "")).strip()
        email = task.get("email")
        if not user_id:
            continue
        for inbound in vless_inbounds:
            clients = inbound.setdefault("settings", {}).setdefault("clients", [])
            if action == "add_key":
                if not any(c.get("id") == user_id for c in clients):
                    item = {"id": user_id, "flow": "xtls-rprx-vision"}
                    if email:
                        item["email"] = email
                    clients.append(item)
                    changed = True
            elif action == "del_key":
                new_clients = [c for c in clients if c.get("id") != user_id]
                if len(new_clients) != len(clients):
                    inbound["settings"]["clients"] = new_clients
                    changed = True
    if changed:
        try:
            write_json_atomic(xray_config_path, cfg)
            # Reload xray via systemd
            rc = subprocess.call(["systemctl", "reload", "xray"])  # type: ignore
            if rc != 0:
                subprocess.call(["systemctl", "restart", "xray"])  # fallback
        except Exception:
            pass


async def ack_tasks(central: str, token: str, task_ids: List[int], status: str = "done") -> None:
    for tid in task_ids:
        try:
            await http_post_json(f"{central}/tasks/{tid}/ack", token, {"status": status})
        except Exception:
            pass


async def run_loop() -> None:
    env = load_env(ENV_PATH)
    central = env.get("CENTRAL_API_BASE", "").rstrip("/")
    token = env.get("SERVER_TOKEN", "")
    server_id = env.get("SERVER_ID", os.uname().nodename)
    heartbeat_interval = int(env.get("HEARTBEAT_INTERVAL", "30") or 30)
    xray_port = int(env.get("XRAY_PORT", "443") or 443)
    ping_target = env.get("PING_TARGET", "1.1.1.1")
    xray_config = env.get("XRAY_CONFIG", "/etc/xray/config.json")
    net_iface = env.get("NET_IFACE", "") or (await default_iface())
    agent_listen = env.get("AGENT_LISTEN") or "127.0.0.1:8081"

    last_ts = 0
    last_rx_bytes = last_tx_bytes = last_rx_pkts = last_tx_pkts = 0
    last_active_opens = last_passive_opens = 0

    log(f"start: interval={heartbeat_interval}s, central={central or 'unset'}, iface={net_iface or 'auto'}, listen={agent_listen}")

    # HTTP server for commands from central (optional direct push)
    async def handle_command(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid json"}, status=400)
        # expected: {tasks: [...]} or a single task
        tasks: List[Dict[str, Any]]
        if isinstance(body, dict) and "tasks" in body and isinstance(body["tasks"], list):
            tasks = body["tasks"]
        elif isinstance(body, dict):
            tasks = [body]
        elif isinstance(body, list):
            tasks = body
        else:
            return web.json_response({"ok": False, "error": "invalid payload"}, status=400)
        apply_tasks(tasks, xray_config)
        return web.json_response({"ok": True})

    app = web.Application()
    app.add_routes([web.post('/command', handle_command)])

    host, port = agent_listen.split(':') if ':' in agent_listen else (agent_listen, '8081')
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, int(port))
    await site.start()

    while True:
        loop_start = datetime.now(timezone.utc).isoformat(timespec="seconds")

        # Basic stats
        uptime_s = int(float(read_proc("/proc/uptime").split()[0] or 0)) if read_proc("/proc/uptime") else 0
        load1 = (read_proc("/proc/loadavg").split()[0] if read_proc("/proc/loadavg") else "0.00")
        meminfo = read_proc("/proc/meminfo")
        mem_total = mem_free = 0
        if meminfo:
            mt = re.search(r"MemTotal:\s+(\d+)", meminfo)
            ma = re.search(r"MemAvailable:\s+(\d+)", meminfo)
            if mt:
                mem_total = int(int(mt.group(1)) / 1024)
            if ma:
                mem_free = int(int(ma.group(1)) / 1024)

        cpu_total, softirq_pct = await cpu_sample()

        # Interface counters
        rx_bytes = rx_pkts = rx_drop = tx_bytes = tx_pkts = tx_drop = 0
        if net_iface:
            rb, rp, _, rd, tb, tp, _, td = read_dev_counters(net_iface)
            rx_bytes, rx_pkts, rx_drop, tx_bytes, tx_pkts, tx_drop = rb, rp, rd, tb, tp, td

        now = int(time.time())
        bw_rx_mbps = bw_tx_mbps = 0.0
        pps_rx = pps_tx = 0
        if last_ts > 0 and now > last_ts and net_iface:
            dt = max(1, now - last_ts)
            bw_rx_mbps = round(((rx_bytes - last_rx_bytes) * 8.0) / (dt * 1_000_000), 2)
            bw_tx_mbps = round(((tx_bytes - last_tx_bytes) * 8.0) / (dt * 1_000_000), 2)
            pps_rx = max(0, int((rx_pkts - last_rx_pkts) / dt))
            pps_tx = max(0, int((tx_pkts - last_tx_pkts) / dt))

        # Connection establishment rate
        active_opens = tcp_ext_value("ActiveOpens")
        passive_opens = tcp_ext_value("PassiveOpens")
        conn_est_rate = 0
        if last_ts > 0 and now > last_ts:
            delta = (active_opens - last_active_opens) + (passive_opens - last_passive_opens)
            dt2 = max(1, now - last_ts)
            conn_est_rate = max(0, int(delta / dt2))

        # Active connections to xray_port
        rc, out_ss, _ = await run_cmd(["ss", "-tn", "state", "established", f"( dport = :{xray_port} )"], timeout=5)
        active_conns = 0
        if rc == 0:
            lines = [ln for ln in out_ss.splitlines() if ln.strip()]
            active_conns = max(0, len(lines) - 1) if len(lines) > 1 else 0

        # Conntrack usage
        ct_count = ct_max = 0
        try:
            ct_count = int(read_proc("/proc/sys/net/netfilter/nf_conntrack_count").strip() or 0)
            ct_max = int(read_proc("/proc/sys/net/netfilter/nf_conntrack_max").strip() or 0)
        except Exception:
            pass
        conntrack_usage_pct = round((ct_count * 100.0 / ct_max), 1) if ct_max > 0 else 0.0

        # Ping latency and loss
        p50, p95, loss = await measure_ping(ping_target)

        bw_total_mbps = round(bw_rx_mbps + bw_tx_mbps, 2)
        pps_total = pps_rx + pps_tx

        loop_ready = datetime.now(timezone.utc).isoformat(timespec="seconds")

        if central and token:
            payload = {
                "server_id": server_id,
                "generated_at": loop_start,
                "ready_at": loop_ready,
                "iface": net_iface,
                "ping_target": ping_target,
                "uptime_s": uptime_s,
                "load1": load1,
                "mem_total_mb": mem_total,
                "mem_free_mb": mem_free,
                "cpu_total_pct": cpu_total,
                "softirq_pct": softirq_pct,
                "bw_rx_mbps": bw_rx_mbps,
                "bw_tx_mbps": bw_tx_mbps,
                "bw_total_mbps": bw_total_mbps,
                "pps_rx": pps_rx,
                "pps_tx": pps_tx,
                "pps_total": pps_total,
                "conn_est_rate_s": conn_est_rate,
                "active_conns": active_conns,
                "conntrack_usage_pct": conntrack_usage_pct,
                "rx_dropped": rx_drop,
                "tx_dropped": tx_drop,
                "latency_p50_ms": p50,
                "latency_p95_ms": p95,
                "packet_loss_pct": loss,
            }
            await http_post_json(f"{central}/heartbeat", token, payload)

        # tasks
        if central and token:
            tasks = await http_get_json(f"{central}/tasks?server_id={server_id}", token)
            if isinstance(tasks, list) and tasks:
                apply_tasks(tasks, xray_config)
                done_ids = [int(t.get("task_id")) for t in tasks if isinstance(t.get("task_id"), int)]
                if done_ids:
                    await ack_tasks(central, token, done_ids, status="done")

        # update counters
        last_ts = now
        last_rx_bytes, last_tx_bytes = rx_bytes, tx_bytes
        last_rx_pkts, last_tx_pkts = rx_pkts, tx_pkts
        last_active_opens, last_passive_opens = active_opens, passive_opens

        await asyncio.sleep(max(1, heartbeat_interval))


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        asyncio.run(run_loop())
    except KeyboardInterrupt:
        pass


