# R2BEWI SDK

**Kit d'infrastructure pour déployer et opérer une plateforme robotique distribuée basée sur K3s et ROS2.**

---

## Ce que contient ce dépôt

| Module | Rôle |
|---|---|
| `bootstrap/` | CLI `r2bewi` — provisioning du cluster K3s (init, deploy, enroll, labels, uninstall) |
| `containers/` | Construction et publication des images Docker des services ROS2 |
| `docker/` | Environnement de build conteneurisé (Ubuntu 24.04) |

---

## Architecture cible

Trois classes de nœuds :

| Classe | Architecture | Rôle |
|---|---|---|
| **Bastion** | x86 | Point central : K3s server, bridge réseau, dnsmasq, registry OCI |
| **Nœud motion / I/O** | ARM | Commande moteur, interfaces matérielles, contrôle bas niveau |
| **Nœud perception** | ARM + GPU | Acquisition caméra, traitement image, inférence |

```
                  ┌────────────────────────────────┐
                  │  Bastion x86  (K3s server)     │
                  │  r2bewi · dnsmasq · NAT        │
                  │  registry OCI (:5000)          │
                  └────────────────┬───────────────┘
                                   │ LAN robot (192.168.82.0/24)
           ┌───────────────────────┴───────────────────────┐
           │                                               │
  ┌────────▼───────┐                             ┌─────────▼────────┐
  │  ARM motion    │                             │  ARM + GPU       │
  │  K3s agent     │                             │  K3s agent       │
  └────────────────┘                             └──────────────────┘
```

---

## Prérequis

### Bastion

- Ubuntu 22.04+
- Paquet `r2bewi` installé (`.deb`)
- Accès internet sortant vers `get.k3s.io`

### Agents

- Ubuntu 20.04+ (ou JetPack 5/6 pour Jetson)
- SSH accessible depuis le bastion
- `curl` disponible (installé automatiquement si absent)

### Développement

- Docker avec BuildKit
- Ou utiliser l'environnement conteneurisé : `docker compose -f docker/build/compose.yaml run r2bewi-build`

---

## Commandes disponibles

### Bootstrap (CLI r2bewi)

| Commande | Description |
|---|---|
| `make bootstrap-build` | Construit le binaire auto-extractible (`dist/r2bewi`) |
| `make bootstrap-test` | Lance la suite pytest |
| `make bootstrap-lint` | Vérifie la syntaxe Python |

> Avant `make bootstrap-test` : `pip install -r bootstrap/requirements-dev.txt`

### Containers (Docker)

| Commande | Description |
|---|---|
| `make containers-build` | Construit les images Docker des services |
| `make containers-push` | Publie les images sur le registry du bastion |
| `make containers-clean` | Supprime les images locales |
| `make containers-test` | Lint des Dockerfiles (hadolint) |

### Accès SSH

| Commande | Description |
|---|---|
| `make ssh-setup` | Installe la clé SSH locale sur le bastion (une seule fois) |

### Variables

| Variable | Défaut | Description |
|---|---|---|
| `REGISTRY_HOST` | `registry.r2bewi.internal` | Hôte du registry OCI |
| `REGISTRY_PORT` | `5000` | Port du registry |
| `IMAGE_TAG` | `latest` | Tag de publication des images |
| `BASTION_HOST` | `bastion.r2bewi.internal` | Nom DNS du bastion |
| `BOOTSTRAP_USER` | `ubuntu` | User SSH d'usine (pour `ssh-setup`) |
| `SSH_USER` | `iobewi` | User SSH cible sur le bastion |

---

## Démarrage rapide

### 1. Installer le bastion

```bash
sudo r2bewi init r2bewi --kind server --ip 192.168.82.1
# Éditer /etc/r2bewi/nodes/r2bewi/netplan.yaml (SSID, interface, IP)
sudo r2bewi deploy r2bewi
sudo r2bewi enroll r2bewi
```

### 2. Enrôler un agent

```bash
sudo r2bewi init r2arm01 --kind agent --ip 192.168.82.101
# Remplir /etc/r2bewi/nodes/r2arm01/node-profile.yaml
sudo r2bewi validate r2arm01
sudo r2bewi deploy r2arm01 --ip 192.168.82.101
sudo r2bewi enroll r2arm01 --ip 192.168.82.101
```

### 3. Construire et publier les images de services

```bash
make containers-build
make containers-push
```

---

## Références

- [`docs/runbook.md`](docs/runbook.md) — procédure complète d'installation
- [`docs/labels.md`](docs/labels.md) — convention de labels K3s `r2bewi.io/`
- [`docs/whitebook.md`](docs/whitebook.md) — vision architecture R2BEWI
- [`docs/contributing.md`](docs/contributing.md) — standards code, tests, hooks pré-commit
- [`containers/README.md`](containers/README.md) — build et publication des images
