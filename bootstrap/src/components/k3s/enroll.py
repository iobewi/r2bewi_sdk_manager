"""
role:
    Installer K3s sur un nœud — server (local) ou agent (distant).

responsibilities:
    server : installer K3s server, attendre l'API, déployer les manifests
    agent  : pousser les fichiers K3s, installer K3s agent, attendre Ready, appliquer labels

does_not:
    - appliquer la configuration système (géré par node/deploy.py)
"""
from __future__ import annotations

import datetime
import os
import shutil
import sys
import time
from pathlib import Path

from ...system.base import (
    NODES_DIR, _svc, error, get_kind, info, ok,
    push_file, resolve_ip, run as _run_cmd, run_ssh, section, ssh_target, warn,
)
from ...system.subprocess_utils import ssh_quote as _ssh_quote
from ...system.iobewi_setup import create_iobewi_on_agent, ensure_iobewi_key
from ...system.profile import load_labels as _load_profile_labels
from ...core.validate import validate_node_dir


def register(sub) -> None:
    p = sub.add_parser("enroll", help="Installer K3s : server (local) ou agent (distant via SSH)")
    p.add_argument("hostname", metavar="HOSTNAME")
    p.add_argument("--ip", metavar="ADDRESS", default=None,
                   help="IP de l'agent (absent → server local)")
    p.add_argument("--bootstrap-user", metavar="USER", default=None)
    p.add_argument("--nvidia", action="store_true", default=False)


K3S_CONFIG_FILE = Path("/etc/rancher/k3s/config.yaml")
K3S_TOKEN_FILE = Path("/var/lib/rancher/k3s/server/node-token")
K3S_AGENT_CONFIG_DIR = "/etc/rancher/k3s"
K3S_CONTAINERD_DIR = "/var/lib/rancher/k3s/agent/etc/containerd"
K3S_INSTALL_URL = "https://get.k3s.io"
K3S_READY_TIMEOUT = 120
NODE_READY_TIMEOUT = 90

_CONTAINERD_NVIDIA_CONFIG = """\
version = 2

[plugins."io.containerd.grpc.v1.cri".containerd]
  default_runtime_name = "nvidia"

[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia]
  runtime_type = "io.containerd.runc.v2"

[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia.options]
  BinaryName = "/usr/bin/nvidia-container-runtime"
"""


def run(args) -> None:
    node_dir = NODES_DIR / args.hostname
    if not node_dir.is_dir():
        error(f"Répertoire introuvable : {node_dir}")
        error(f"  Lancer d'abord : sudo r2bewi init {args.hostname} --kind <server|agent>")
        sys.exit(1)

    kind = get_kind(node_dir)
    resolved_ip = resolve_ip(args.hostname, node_dir, args.ip)

    if kind == "server":
        _enroll_server(args.hostname)
    else:
        target = ssh_target(args.hostname, resolved_ip, "iobewi")
        _enroll_agent(args.hostname, node_dir, target, args.bootstrap_user, args.nvidia)


# ── Server ────────────────────────────────────────────────────────────────────

def _enroll_server(hostname: str) -> None:
    section("Préflight server")
    if os.geteuid() != 0:
        error("enroll doit être exécuté en root (sudo)")
        sys.exit(1)
    if os.environ.get("SUDO_USER") != "iobewi":
        error("enroll doit être lancé par 'iobewi' : sudo r2bewi enroll ...")
        error(f"  User détecté : {os.environ.get('SUDO_USER')!r}")
        sys.exit(1)
    for tool in ("curl", "systemctl"):
        from ...system.base import which
        if not which(tool):
            error(f"Outil requis introuvable : {tool}")
            error(f"  → sudo apt-get install -y {tool}")
            sys.exit(1)
    if not K3S_CONFIG_FILE.exists():
        error(f"Config K3s absente : {K3S_CONFIG_FILE}")
        error(f"  Lancer d'abord : sudo r2bewi deploy {hostname}")
        sys.exit(1)
    if which("k3s") and K3S_TOKEN_FILE.exists():
        info("K3s server déjà initialisé")
        _log_nodes()
        ok("Rien à faire — déjà initialisé")
        sys.exit(0)
    info(f"hostname : {hostname}")
    ok("Préflight OK")

    section("Installation K3s server")
    _install_k3s("server")

    section("Attente disponibilité")
    _wait_k3s_ready(timeout=K3S_READY_TIMEOUT)

    section("Validation")
    if not K3S_TOKEN_FILE.exists():
        error(f"Token introuvable : {K3S_TOKEN_FILE}")
        sys.exit(1)
    info(f"Token présent : {K3S_TOKEN_FILE}")
    if not _svc.is_active("k3s"):
        error("Service k3s non actif")
        sys.exit(1)
    info("Service k3s actif")
    _log_nodes()
    ok("Validation OK")

    section("Manifests K3s")
    _deploy_manifests()

    ok("=== enroll server terminé ===")
    print()
    print("Prochaine étape — enrôler les agents :")
    print("  sudo r2bewi init <hostname> --kind agent --ip <IP>")
    print("  sudo r2bewi deploy <hostname> --ip <IP>")
    print("  sudo r2bewi enroll <hostname> --ip <IP>")


# ── Agent ─────────────────────────────────────────────────────────────────────

def _enroll_agent(
    hostname: str,
    node_dir: Path,
    target: str,
    bootstrap_user: str | None,
    nvidia: bool,
) -> None:
    section("Préflight local")
    if os.geteuid() != 0:
        error("enroll doit être exécuté en root (sudo)")
        sys.exit(1)
    if os.environ.get("SUDO_USER") != "iobewi":
        error("enroll doit être lancé par 'iobewi' : sudo r2bewi enroll ...")
        error(f"  User détecté : {os.environ.get('SUDO_USER')!r}")
        sys.exit(1)
    from ...system.base import which
    if not which("ssh"):
        error("Outil requis introuvable : ssh")
        error("  → sudo apt-get install -y ssh")
        sys.exit(1)
    if not K3S_TOKEN_FILE.exists():
        error(f"Token K3s introuvable : {K3S_TOKEN_FILE}")
        error("Exécuter d'abord : sudo r2bewi enroll <hostname-server>")
        sys.exit(1)
    iobewi_key = ensure_iobewi_key()
    info(f"Cible    : {target}")
    info(f"Hostname : {hostname}")
    ok("Préflight local OK")

    # Bootstrap : connexion initiale avec l'utilisateur d'usine si fourni
    if bootstrap_user and bootstrap_user != "iobewi":
        ip = target.split("@")[1]
        bootstrap_target = ssh_target(hostname, ip, bootstrap_user)
        section(f"Bootstrap iobewi via {bootstrap_user}")
        create_iobewi_on_agent(bootstrap_target, iobewi_key)
        ok(f"Utilisateur iobewi créé sur {ip}")
        target = ssh_target(hostname, ip, "iobewi")

    section("Validation")
    if not validate_node_dir(node_dir, kind=get_kind(node_dir)):
        error("Validation échouée — corriger les erreurs avant d'enrôler")
        sys.exit(1)
    ok("Validation OK")

    section("Préflight distant")
    _preflight_remote(target, iobewi_key, nvidia)

    section("Idempotence")
    if _node_in_cluster(hostname):
        info(f"Nœud {hostname!r} déjà dans le cluster")
        _apply_labels(hostname)
        ok("Déjà enrôlé — labels mis à jour")
        sys.exit(0)

    section("Fichiers K3s agent")
    _push_k3s_files(node_dir, target, iobewi_key, nvidia)

    section("Installation K3s agent")
    _install_k3s("agent", target=target, identity=iobewi_key)

    section("Attente node Ready")
    _wait_k3s_ready(hostname=hostname, timeout=NODE_READY_TIMEOUT)

    section("Labels node")
    _apply_labels(hostname)

    ok(f"=== enroll agent terminé : {hostname} ===")


# ── Briques partagées ─────────────────────────────────────────────────────────

def _install_k3s(
    mode: str,
    target: str | None = None,
    identity: Path | None = None,
) -> None:
    if target is None:
        cmd = f"curl -sfL {K3S_INSTALL_URL} | sh -s - {mode}"
        info(f"Installation K3s {mode} (local)")
        _run_cmd(["sh", "-c", cmd])
    else:
        install_cmd = (
            f"curl -sfL {K3S_INSTALL_URL} "
            f"| INSTALL_K3S_SKIP_START=true sudo sh -s - {mode}"
        )
        info(f"Installation K3s {mode} sur {target}")
        run_ssh(target, install_cmd, identity=identity)
        run_ssh(target, f"sudo systemctl start --no-block k3s-{mode}",
                check=False, identity=identity)
        info(f"Service k3s-{mode} démarré (--no-block)")
    ok(f"K3s {mode} installé")


def _wait_k3s_ready(
    hostname: str | None = None,
    timeout: int = 120,
) -> None:
    if hostname is None:
        cmd = ["k3s", "kubectl", "get", "nodes"]
        label = "K3s API"
        is_ready = lambda r: r.returncode == 0
    else:
        cmd = ["k3s", "kubectl", "get", "node", hostname, "--no-headers"]
        label = f"node {hostname!r}"
        is_ready = lambda r: (
            r.returncode == 0
            and "Ready" in (r.stdout or "")
            and "NotReady" not in (r.stdout or "")
        )

    info(f"Attente {label} (timeout {timeout}s)...")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _run_cmd(cmd, check=False, capture=True)
        if is_ready(result):
            ok(f"{label} prêt")
            return
        remaining = int(deadline - time.monotonic())
        info(f"  Pas encore prêt — réessai dans 5s ({remaining}s restants)")
        time.sleep(5)

    error(f"{label} n'a pas répondu en {timeout}s")
    error(f"  → Vérifier : sudo journalctl -u k3s -n 50")
    error(f"  → Vérifier : sudo systemctl status k3s")
    sys.exit(1)


def _apply_labels(hostname: str) -> None:
    node_dir = NODES_DIR / hostname
    labels = ["node-role.kubernetes.io/worker=worker"]
    labels += _load_profile_labels(node_dir)

    for label in labels:
        _run_cmd(["k3s", "kubectl", "label", "node", hostname, label, "--overwrite"], check=False)
        info(f"  {hostname} → {label}")
    ok("Labels appliqués")
    _log_node(hostname)


def _preflight_remote(target: str, iobewi_key: Path, nvidia: bool) -> None:
    result = run_ssh(target, "echo ok", check=False, capture=True, identity=iobewi_key)
    if result.returncode != 0:
        error(f"Cible SSH inaccessible : {target}")
        sys.exit(1)
    info(f"SSH OK : {target}")

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    run_ssh(target, f"sudo date -u -s {_ssh_quote(now)}", check=False, identity=iobewi_key)
    info(f"Horloge agent synchronisée depuis le bastion ({now} UTC)")

    result = run_ssh(target, "command -v sudo >/dev/null && echo ok",
                     check=False, capture=True, identity=iobewi_key)
    if "ok" not in (result.stdout or ""):
        error("sudo manquant sur la cible")
        sys.exit(1)


    result = run_ssh(target, "curl -sf --max-time 10 https://get.k3s.io -o /dev/null && echo ok",
                     check=False, capture=True, identity=iobewi_key)
    if "ok" not in (result.stdout or ""):
        error("L'agent ne peut pas atteindre https://get.k3s.io")
        error("  Vérifier que le NAT est actif sur le bastion :")
        error("  sudo r2bewi deploy r2bewi   (applique la règle iptables masquerade)")
        sys.exit(1)
    info("Connectivité internet OK (get.k3s.io joignable)")

    if nvidia:
        result = run_ssh(target, "command -v nvidia-container-runtime >/dev/null && echo ok",
                         check=False, capture=True, identity=iobewi_key)
        if "ok" not in (result.stdout or ""):
            error("nvidia-container-runtime manquant — JetPack installé ?")
            sys.exit(1)
        info("nvidia-container-runtime présent")
    ok("Préflight distant OK")


def _node_in_cluster(hostname: str) -> bool:
    return _run_cmd(["k3s", "kubectl", "get", "node", hostname],
               check=False, capture=True).returncode == 0


def _push_k3s_files(
    node_dir: Path, target: str, iobewi_key: Path, nvidia: bool
) -> None:
    token = K3S_TOKEN_FILE.read_text().strip()
    run_ssh(target, f"sudo mkdir -p {K3S_AGENT_CONFIG_DIR}", identity=iobewi_key)

    config_content = (node_dir / "k3s-config.yaml").read_text().replace("__TOKEN__", token)
    info(f"Push config.yaml → {target}")
    push_file(target, f"{K3S_AGENT_CONFIG_DIR}/config.yaml", config_content, identity=iobewi_key)

    registries_content = (node_dir / "registries.yaml").read_text()
    info(f"Push registries.yaml → {target}")
    push_file(target, f"{K3S_AGENT_CONFIG_DIR}/registries.yaml", registries_content, identity=iobewi_key)

    if nvidia:
        run_ssh(target, f"sudo mkdir -p {K3S_CONTAINERD_DIR}", identity=iobewi_key)
        push_file(target, f"{K3S_CONTAINERD_DIR}/config.toml.tmpl",
                  _CONTAINERD_NVIDIA_CONFIG, identity=iobewi_key)
        info("Push containerd NVIDIA config")

    ok("Fichiers K3s agent poussés")


def _deploy_manifests() -> None:
    dest_dir = Path("/var/lib/rancher/k3s/server/manifests/r2bewi")
    system_manifests = Path("/usr/share/r2bewi/manifests")
    local_manifests = Path(os.environ.get("R2BEWI_SELF") or sys.argv[0]).resolve().parent.parent / "manifests"

    if system_manifests.is_dir():
        src_dir = system_manifests
    elif local_manifests.is_dir():
        src_dir = local_manifests
        info(f"Manifests (développement) : {src_dir}")
    else:
        warn("Aucun répertoire de manifests — étape ignorée")
        return

    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for yaml_file in sorted(src_dir.glob("*.yaml")):
        shutil.copy2(yaml_file, dest_dir / yaml_file.name)
        info(f"  {yaml_file.name} → {dest_dir}")
        copied += 1
    if copied:
        ok(f"{copied} manifest(s) déployé(s)")
    else:
        info(f"Aucun manifest *.yaml dans {src_dir}")


def _log_nodes() -> None:
    result = _run_cmd(["k3s", "kubectl", "get", "nodes"], check=False, capture=True)
    if result.returncode == 0:
        for line in result.stdout.strip().splitlines():
            info(f"  {line}")


def _log_node(hostname: str) -> None:
    result = _run_cmd(["k3s", "kubectl", "get", "node", hostname], check=False, capture=True)
    if result.returncode == 0:
        for line in (result.stdout or "").strip().splitlines():
            info(f"  {line}")
