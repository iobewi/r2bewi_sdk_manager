"""
role:
    Read-only system state queries shared by status and idempotence checks.

responsibilities:
    - check service liveness (local and remote)
    - detect k3s installation and node readiness
    - inspect network interface addresses
    - test SSH reachability
    - check file and key presence

does_not:
    - modify any system state
    - raise exceptions (all functions return bool, str, or None on failure)

side_effects:
    - none (all functions are pure observers)

idempotency:
    - fully idempotent; safe to call repeatedly

review_focus:
    - node_ready() parses raw kubectl output — "Ready" but not "NotReady"
    - ssh_reachable() and remote_service_active() use ConnectTimeout=5;
      callers should handle slow networks gracefully
    - bridge_address() parses `ip -o -4 addr` output; returns None if
      interface is absent or has no IPv4 address
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def service_active(name: str) -> bool:
    r = subprocess.run(
        ["systemctl", "is-active", "--quiet", name],
        capture_output=True,
    )
    return r.returncode == 0


def k3s_installed() -> bool:
    return _which("k3s")


def k3s_token_present() -> bool:
    return Path("/var/lib/rancher/k3s/server/node-token").exists()


def node_ready(hostname: str) -> tuple[bool, str]:
    """Retourne (is_ready, ligne brute kubectl). Requiert k3s installé."""
    r = subprocess.run(
        ["k3s", "kubectl", "get", "node", hostname, "--no-headers"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return False, ""
    line = r.stdout.strip()
    return "Ready" in line and "NotReady" not in line, line


def bridge_address(interface: str) -> str | None:
    """Retourne l'adresse CIDR de l'interface si UP (ex: '192.168.82.1/24'), sinon None."""
    r = subprocess.run(
        ["ip", "-o", "-4", "addr", "show", interface],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not r.stdout.strip():
        return None
    parts = r.stdout.split()
    for i, part in enumerate(parts):
        if part == "inet" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def sysctl_get(key: str) -> str | None:
    r = subprocess.run(["sysctl", "-n", key], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def ssh_key_present(path: str = "/root/.ssh/id_ed25519") -> bool:
    return Path(path).exists()


def file_present(path: str) -> bool:
    return Path(path).exists()


def ssh_reachable(target: str) -> bool:
    r = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
         "-o", "StrictHostKeyChecking=no", target, "echo ok"],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0 and "ok" in r.stdout


def remote_service_active(target: str, name: str) -> bool:
    r = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
         "-o", "StrictHostKeyChecking=no",
         target, f"systemctl is-active --quiet {name}"],
        capture_output=True,
    )
    return r.returncode == 0


def _which(cmd: str) -> bool:
    return any(
        (Path(d) / cmd).is_file()
        for d in os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin").split(":")
        if d
    )
