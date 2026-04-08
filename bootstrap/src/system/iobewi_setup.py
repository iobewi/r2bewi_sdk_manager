"""
role:
    Créer le user iobewi sur un agent et établir la confiance SSH.

responsibilities:
    - générer la clé SSH ed25519 de iobewi sur le bastion si absente
    - copier la clé publique sur l'agent via le bootstrap_user
    - créer le user iobewi avec NOPASSWD sudo
    - installer la clé publique de iobewi dans authorized_keys

does_not:
    - installer K3s (géré par enroll)
    - appliquer la configuration système (géré par deploy)

pre:
    - bootstrap_user a accès SSH à l'agent (mot de passe ou clé)
    - bootstrap_user peut sudo sur l'agent (interactif OK)

post:
    - iobewi@<ip> accessible par clé SSH sans mot de passe
    - iobewi a NOPASSWD sudo sur l'agent
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

from .log import error, info, ok, warn
from .subprocess_utils import run, run_ssh, ssh_quote


def ensure_iobewi_key(sudo_user: str | None = None) -> Path:
    """
    Retourne le chemin de la clé ed25519 de iobewi (ou du sudo_user).
    La génère si elle est absente.
    """
    user = sudo_user or os.environ.get("SUDO_USER", "iobewi")
    key = Path(f"/home/{user}/.ssh/id_ed25519")
    if not key.exists():
        info(f"Génération clé SSH ed25519 pour '{user}'")
        key.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", f"{user}@r2bewi",
             "-f", str(key)])
        run(["chown", "-R", f"{user}:{user}", str(key.parent)])
        ok(f"Clé SSH générée : {key}")
    return key


def create_iobewi_on_agent(
    bootstrap_target: str,
    iobewi_key: Path,
    iobewi_user: str = "iobewi",
) -> None:
    """
    Crée le user iobewi sur l'agent en utilisant uniquement bootstrap_target.

    Séquence :
      1. Connexion SSH avec le bootstrap_user (mot de passe interactif)
      2. Création du user iobewi via sudo
      3. Copie de la clé publique dans /home/iobewi/.ssh/authorized_keys via sudo tee
      4. NOPASSWD sudo pour iobewi

    Idempotent : si iobewi est déjà accessible par clé depuis le bastion, ne fait rien.
    """
    ip = bootstrap_target.split("@")[1]
    iobewi_target = f"{iobewi_user}@{ip}"

    # Test idempotence : iobewi accessible par clé ?
    test = run_ssh(iobewi_target, "echo ok", check=False, capture=True,
                   identity=iobewi_key, extra_opts=["-o", "BatchMode=yes"])
    if test.returncode == 0:
        info(f"User '{iobewi_user}' déjà accessible par clé — rien à faire")
        return

    key_pub = Path(str(iobewi_key) + ".pub")
    if not key_pub.exists():
        error(f"Clé publique absente : {key_pub}")
        sys.exit(1)
    pub_key_content = key_pub.read_text().strip()
    # Encode la clé en base64 pour éviter tout problème de quoting shell
    # (commentaires de clé pouvant contenir des apostrophes ou caractères spéciaux)
    pub_key_b64 = base64.b64encode(pub_key_content.encode()).decode()

    info(f"Connexion avec {bootstrap_target} — mot de passe requis une seule fois")

    script = f"""\
set -e
PUB_KEY=$(echo '{pub_key_b64}' | base64 -d)
# Créer iobewi si absent
if ! id {iobewi_user} > /dev/null 2>&1; then
    sudo useradd -m -s /bin/bash -G sudo {iobewi_user}
fi
sudo passwd -l {iobewi_user}
# Préparer .ssh
sudo mkdir -p /home/{iobewi_user}/.ssh
sudo chmod 700 /home/{iobewi_user}/.ssh
sudo touch /home/{iobewi_user}/.ssh/authorized_keys
sudo chmod 600 /home/{iobewi_user}/.ssh/authorized_keys
sudo chown -R {iobewi_user}:{iobewi_user} /home/{iobewi_user}/.ssh
# Copier la clé publique
sudo grep -qF "$PUB_KEY" /home/{iobewi_user}/.ssh/authorized_keys \
    || printf '%s\n' "$PUB_KEY" | sudo tee -a /home/{iobewi_user}/.ssh/authorized_keys > /dev/null
# NOPASSWD sudo
echo '{iobewi_user} ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/r2bewi > /dev/null
sudo chmod 440 /etc/sudoers.d/r2bewi
echo "OK"
"""
    script_b64 = base64.b64encode(script.encode()).decode()
    run_ssh(bootstrap_target, f"echo {ssh_quote(script_b64)} | base64 -d | sudo bash")
    ok(f"User '{iobewi_user}' créé, clé installée, NOPASSWD configuré")


def setup_ssh_trust(target: str, iobewi_key: Path) -> None:
    """Installe la clé publique de iobewi dans authorized_keys de la cible."""
    key_pub = Path(str(iobewi_key) + ".pub")
    if not key_pub.exists():
        warn("Clé publique absente — ssh-copy-id ignoré")
        return
    result = run(["ssh-copy-id", "-i", str(key_pub), "-o", f"IdentityFile={iobewi_key}",
                  target], check=False)
    if result.returncode != 0:
        warn("ssh-copy-id échoué — confiance supposée déjà établie")
    else:
        ok("Clé publique installée sur la cible")
