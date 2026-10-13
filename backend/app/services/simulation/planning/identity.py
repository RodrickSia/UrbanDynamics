"""Local process identity: PID alone and stale heartbeat are not death proofs."""
import hashlib
import json
from pathlib import Path
import socket
import os
import math

import psutil


def snapshot(pid):
    process = psutil.Process(pid)
    return {"pid": pid, "parent_pid": process.ppid(), "created_at": process.create_time(), "host": socket.gethostname(),
            "command_hash": hashlib.sha256(json.dumps(process.cmdline()).encode()).hexdigest(),
            "cwd": process.cwd()}


def state(identity):
    if not isinstance(identity, dict) or identity.get("host") != socket.gethostname():
        return "unverifiable"
    if (type(identity.get("pid")) is not int or identity["pid"] <= 0
            or type(identity.get("created_at")) not in (int, float)
            or not 0 <= identity["created_at"] <= 1e15
            or not math.isfinite(identity["created_at"])
            or not isinstance(identity.get("command_hash"), str)
            or len(identity["command_hash"]) != 64
            or not isinstance(identity.get("cwd"), str) or not identity["cwd"]):
        return "unverifiable"
    try:
        process = psutil.Process(identity["pid"])
        if abs(process.create_time()-identity["created_at"]) > .001:
            return "stopped"  # Original PID identity ended; never touch its replacement.
        if process.status() == psutil.STATUS_ZOMBIE:
            return "stopped"
        if hashlib.sha256(json.dumps(process.cmdline()).encode()).hexdigest() != identity["command_hash"]:
            return "unverifiable"
        return "alive"
    except psutil.NoSuchProcess:
        return "stopped"
    except (psutil.AccessDenied, OSError, KeyError, ValueError, TypeError):
        return "unverifiable"


def snapshot_tree(pid):
    result = snapshot(pid)
    result["descendants"] = []
    for child in psutil.Process(pid).children(recursive=True):
        try:
            # Windows creates a console host alongside the actual Python child.
            # It is not an engine and its cwd is SystemRoot; do not target it.
            console = Path(os.getenv("SystemRoot", r"C:\Windows"))/"System32"/"conhost.exe"
            if os.name == "nt" and Path(child.exe()).resolve() == console.resolve():
                continue
            result["descendants"].append(snapshot(child.pid))
        except psutil.NoSuchProcess:
            pass
    return result


def _stop_single(identity):
    status = state(identity)
    if status == "stopped":
        return True
    if status != "alive":
        return False
    process = psutil.Process(identity["pid"])
    if abs(process.create_time()-identity["created_at"]) > .001:
        return True
    try:
        if Path(process.cwd()).resolve() != Path(identity["cwd"]).resolve():
            return False
        process.terminate()
        process.wait(timeout=5)
    except psutil.TimeoutExpired:
        if state(identity) != "alive":
            return state(identity) == "stopped"
        process.kill()
        process.wait(timeout=5)
    except psutil.NoSuchProcess:
        pass
    except (psutil.AccessDenied, OSError):
        return False
    return state(identity) == "stopped"


def stop_orphan(identity, root):
    """Stop the verified owned tree, including Windows Python launchers.

    Recovery must first prove the worker stopped. The runner may call this
    for its own child on cancel/timeout. Stored descendants cover the case
    where the launcher already exited but its actual engine is still alive.
    """
    status = state(identity)
    if status == "unverifiable" or Path(identity["cwd"]).resolve().parent != root.resolve():
        return False
    members = list(identity.get("descendants", []))
    if status == "alive":
        try:
            members += snapshot_tree(identity["pid"])["descendants"]
        except psutil.NoSuchProcess:
            pass
    if any(state(member) == "unverifiable" or type(member.get("parent_pid")) is not int for member in members):
        return False
    members = list({(p["pid"], p["created_at"]): p for p in members}.values())
    parents = {identity["pid"]} | {p["pid"] for p in members}
    if any(p["parent_pid"] not in parents or Path(p["cwd"]).resolve() != Path(identity["cwd"]).resolve() for p in members):
        return False
    for member in reversed(members):
        if not _stop_single(member):
            return False
    return _stop_single(identity)
