# bootstrap

CLI R2BEWI — gestion de la stack robotique distribuée K3s.

## Responsabilité

Le paquet `.deb` installe `r2bewi` sur le bastion. Il expose les commandes :

| Commande | Rôle |
|---|---|
| `init` | Génère les fichiers de config dans `/etc/r2bewi/nodes/<hostname>/` |
| `deploy` | Applique la configuration système (hostname, swap, réseau, fichiers) |
| `enroll` | Installe K3s et intègre le nœud au cluster |
| `validate` | Vérifie les fichiers de config avant de toucher au système |
| `render-labels` | Visualise les labels K3s dérivés du profil, sans modification |
| `status` | Affiche l'état courant (réseau, services, K3s, fichiers, sauvegardes) |
| `update` | Met à jour les labels K3s sans ré-enrôler |
| `uninstall` | Désinstalle K3s et restaure les fichiers d'origine |
| `headlamp-token` | Génère un token d'accès Headlamp pour le tableau de bord K3s |
| `wg-peer` | Gère les peers WireGuard (ajout / suppression) |

## Séquence d'utilisation

```
# 1. Générer les fichiers de config du nœud
sudo r2bewi init <hostname> --kind <server|agent> [--ip <IP>]

# 2. Éditer les fichiers si besoin
ls /etc/r2bewi/nodes/<hostname>/

# 3. Appliquer la configuration système
sudo r2bewi deploy <hostname>               # local (server)
sudo r2bewi deploy <hostname> --ip <IP>     # distant (agent)

# 4. Installer K3s
sudo r2bewi enroll <hostname>               # server (local)
sudo r2bewi enroll <hostname> --ip <IP>     # agent (distant via SSH)
```

## Structure

```
bootstrap/
├── src/
│   ├── cli.py                    — point d'entrée + dispatch argparse
│   ├── core/                     — kernel r2bewi
│   │   ├── init.py, deploy.py, validate.py, status.py
│   │   ├── catalog/labels.yaml   — source de vérité des labels r2bewi.io/
│   │   └── defaults/server|agent/node-profile.yaml
│   ├── components/               — composants pluggables (modèle ESP-IDF)
│   │   ├── chrony/               — NTP
│   │   ├── dnsmasq/              — DNS/DHCP
│   │   ├── k3s/                  — orchestrateur K3s (enroll, labels, uninstall…)
│   │   ├── nat/                  — NAT masquerade iptables
│   │   ├── netplan/              — configuration réseau bridge
│   │   ├── registry/             — registry OCI local sur LVM
│   │   ├── sysctl/               — paramètres noyau
│   │   └── wireguard/            — VPN WireGuard
│   └── system/                   — abstractions OS
│       ├── base.py               — imports partagés
│       ├── log.py                — section / info / ok / warn / error
│       ├── component.py          — découverte et chargement des composants
│       ├── profile.py            — validate_profile(), profile_to_labels()
│       ├── helpers.py            — NODES_DIR, get_kind(), ssh_target()
│       ├── subprocess_utils.py   — run(), run_ssh(), push_file()
│       ├── state.py              — lectures d'état système (non-destructif)
│       ├── backup.py             — sauvegarde/restauration avant écrasement
│       └── debian/               — abstraction Debian/Ubuntu
│           ├── packages.py       — install_packages() agrégé par composant
│           ├── services.py       — enable(), restart(), is_active()
│           └── packaging/        — DEBIAN/control, postinst, prerm, launcher
├── tests/                        — pytest
└── Makefile                      — build, deb, lint, test
```

Chaque composant déclare dans son `component.yaml` :
- `packages` — paquets système installés par `r2bewi deploy`
- `node_files` — fichiers poussés depuis le node dir vers le système
- `managed_paths` — chemins gérés (pour `status` et `uninstall`)

## Build

```bash
make build    # → dist/r2bewi (binaire auto-extractible)
make deb      # → dist/r2bewi_*.deb
make test     # suite pytest
make lint     # vérification syntaxe Python
make clean    # supprime dist/
```

## Sauvegardes automatiques

Avant toute écriture de fichier système, `deploy` sauvegarde la version existante
dans `/var/lib/r2bewi/backup/`. La commande `uninstall` restaure ces sauvegardes
si elles existent, sinon supprime le fichier généré.

## Références

- [`../docs/runbook.md`](../docs/runbook.md) — procédure complète d'installation
- [`../docs/labels.md`](../docs/labels.md) — convention de labels K3s `r2bewi.io/`
