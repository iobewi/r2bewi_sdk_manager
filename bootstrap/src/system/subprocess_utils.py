"""
role:
    Local and remote command execution primitives used by all system modules.

responsibilities:
    - run local commands with optional output capture
    - run commands on a remote host via SSH
    - push file content to a remote path via SSH + sudo tee

does_not:
    - manage SSH key setup (handled by prepare_bastion)
    - provide shell expansion or piping (callers use sh -c explicitly)

side_effects:
    - run(): executes arbitrary local subprocesses
    - run_ssh(): executes arbitrary remote subprocesses
    - push_file(): writes to a remote file as root (via sudo tee)

review_focus:
    - push_file uses sudo tee — the remote user must have passwordless sudo
    - run(check=True) raises CommandError on non-zero exit; callers using
      check=False must handle returncode themselves
    - remote_cmd in run_ssh is passed as a single shell string to SSH —
      avoid embedding untrusted input without quoting
"""
from __future__ import annotations

import shlex
import subprocess
import sys
from typing import Sequence


def ssh_quote(value: str) -> str:
    """Quote une valeur pour une insertion sûre dans une commande shell distante."""
    return shlex.quote(value)


class CommandError(RuntimeError):
    def __init__(self, cmd: Sequence[str], returncode: int, stderr: str) -> None:
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"Command failed (exit {returncode}): {' '.join(cmd)}\n{stderr}"
        )


def run(
    cmd: Sequence[str],
    *,
    check: bool = True,
    capture: bool = False,
    input: str | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    """
    purpose:
        Execute a local command, streaming or capturing output.

    pre:
        - cmd is a list of strings (not a shell string)

    post:
        - returns CompletedProcess; stdout/stderr populated only if capture=True

    failure_mode:
        - raises CommandError if check=True and returncode != 0
        - raises CommandError (returncode=-1) on timeout
    """
    try:
        result = subprocess.run(
            cmd,
            text=True,
            input=input,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise CommandError(
            list(cmd), -1,
            f"Commande bloquée après {timeout}s\n"
            f"  → Vérifier : sudo journalctl -n 50\n"
            f"  → Tuer : sudo pkill -f {shlex.quote(cmd[0])}",
        )
    if check and result.returncode != 0:
        raise CommandError(list(cmd), result.returncode, result.stderr or "")
    return result


_SSH_OPTS = [
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ConnectTimeout=10",
]


def run_ssh(
    target: str,
    remote_cmd: str,
    *,
    check: bool = True,
    capture: bool = False,
    identity: "str | None" = None,
    extra_opts: "list[str] | None" = None,
    input: str | None = None,
    tty: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command on a remote host via SSH.

    tty=True alloue un pseudo-TTY (-t). Utiliser uniquement pour les commandes
    interactives (ex: sudo avec prompt). En CI ou avec capture=True, laisser
    tty=False (défaut) pour éviter les comportements non déterministes.
    """
    cmd = ["ssh"] + _SSH_OPTS + (extra_opts or [])
    if tty:
        cmd.append("-t")
    if identity:
        cmd += ["-i", str(identity)]
    cmd += [target, remote_cmd]
    return run(cmd, check=check, capture=capture, input=input)


def push_file(target: str, remote_path: str, content: str, identity: "str | None" = None,
              timeout: int | None = None) -> None:
    """
    purpose:
        Write content to a remote file using SSH + sudo tee.

    pre:
        - SSH key trust is established between local root and target
        - remote user has passwordless sudo

    post:
        - remote_path contains content, owned by root

    side_effects:
        - writes to remote disk as root

    failure_mode:
        - raises CommandError on non-zero exit (permission denied, path error)
    """
    ssh_cmd = ["ssh"] + _SSH_OPTS
    if identity:
        ssh_cmd += ["-i", str(identity)]
    ssh_cmd += [target, f"sudo tee {shlex.quote(remote_path)} > /dev/null"]
    try:
        result = subprocess.run(ssh_cmd, input=content, text=True, capture_output=True,
                                timeout=timeout)
    except subprocess.TimeoutExpired:
        raise CommandError(
            ["ssh", target, f"sudo tee {remote_path}"],
            -1,
            f"push_file bloqué après {timeout}s vers {target}:{remote_path}",
        )
    if result.returncode != 0:
        raise CommandError(
            ["ssh", target, f"sudo tee {remote_path}"],
            result.returncode,
            result.stderr or "",
        )
