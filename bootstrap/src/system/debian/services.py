"""
role:
    Thin wrappers around systemctl for service lifecycle management.

side_effects:
    - all mutating functions (enable, start, restart, stop, disable) affect
      systemd state on the local host
    - is_active() is read-only

review_focus:
    - callers must ensure the service unit exists before calling enable/start
    - restart() is used after config changes; verify idempotence at call site
"""
from __future__ import annotations

from ..subprocess_utils import run


def enable(service: str) -> None:
    run(["systemctl", "enable", service])


def start(service: str) -> None:
    run(["systemctl", "start", service])


def restart(service: str) -> None:
    run(["systemctl", "restart", service])


def stop(service: str) -> None:
    run(["systemctl", "stop", service])


def disable(service: str) -> None:
    run(["systemctl", "disable", service])


def is_active(service: str) -> bool:
    result = run(["systemctl", "is-active", "--quiet", service], check=False)
    return result.returncode == 0
