# Runbook R2BEWI-SDK-MANAGER

Procédure d'installation de la stack robotique R2BEWI depuis zéro.

---

## Séquence d'installation

```
1. init     ← génère les fichiers de config dans /etc/r2bewi/nodes/<hostname>/
2. deploy   ← applique la configuration système (hostname, swap, réseau, fichiers)
3. enroll   ← installe K3s et intègre le nœud au cluster
```

Pour le server, toutes les étapes s'exécutent en local sur le bastion.
Pour les agents, `deploy` et `enroll` s'exécutent à distance via SSH.

---

## Prérequis

### Bastion (server)

- Ubuntu 22.04 ou supérieur
- `r2bewi` installé via le paquet `.deb`
- Accès internet sortant vers `get.k3s.io`
- Interfaces réseau : uplink Wi-Fi ou Ethernet + port(s) LAN robot

### Agents

- Ubuntu 20.04 ou supérieur
  - JetPack 5.x → Ubuntu 20.04
  - JetPack 6.x → Ubuntu 22.04
- `curl` et `sudo` disponibles — `curl` est installé automatiquement si absent
- Connecté physiquement au LAN robot
- Accès SSH initial fonctionnel depuis le bastion

---

## 1. Initialiser le bastion (server)

```bash
sudo r2bewi init r2bewi --kind server --ip 192.168.82.1 --ext-if wlan0
```

`--ext-if` désigne l'interface WiFi ou Ethernet externe du bastion (celle qui connecte au LAN infra SDK). dnsmasq y écoute pour résoudre `*.r2bewi.internal` depuis le SDK.

Génère les fichiers dans `/etc/r2bewi/nodes/r2bewi/` :

```
netplan.yaml       ← bridge br0 + uplink
sysctl.conf        ← ip_forward=1
dnsmasq.conf       ← DHCP + DNS LAN
k3s-config.yaml    ← TLS SAN + labels
registries.yaml    ← miroirs de registres
```

Éditer les valeurs spécifiques au site (SSID, PSK, interfaces, IP) :

```bash
ls /etc/r2bewi/nodes/r2bewi/
nano /etc/r2bewi/nodes/r2bewi/netplan.yaml
```

---

## 2. Déployer la configuration système du bastion

```bash
sudo r2bewi deploy r2bewi
```

**Ce qui se passe :**

| Phase | Action |
|---|---|
| Préflight | vérifie root + outils (`hostnamectl`, `netplan`, `systemctl`, `sysctl`) |
| Hostname | `hostnamectl set-hostname r2bewi` |
| Swap | `swapoff -a` + nettoyage `/etc/fstab` |
| Fichiers | netplan → `netplan apply`, sysctl → `sysctl --system`, dnsmasq → restart |
| systemd-resolved | `DNSStubListener=no`, `DNS=127.0.0.1`, `Domains=<domain>` |
| Registry OCI | LV LVM créé + formaté + monté + `apt install docker-registry` + config + service activé |

**Vérifications :**

```bash
ip addr show br0                                  # 192.168.82.1/24
systemctl is-active dnsmasq                       # active
systemctl is-active docker-registry               # active
dig registry.r2bewi.internal @127.0.0.1          # 192.168.82.1
curl http://registry.r2bewi.internal:5000/v2/    # {}  → registry OK
df -h /var/lib/docker-registry                    # volume LVM dédié
```

**Configuration DNS du SDK (une seule fois) :**

```bash
# /etc/systemd/resolved.conf.d/r2bewi.conf
[Resolve]
DNS=<bastion-ip-wifi>
Domains=~r2bewi.internal
```

```bash
sudo systemctl restart systemd-resolved
resolvectl query registry.r2bewi.internal    # doit retourner 192.168.82.1
```

---

## 2b. Volume LVM dédié au registry OCI

> **Automatique.** Aucune action manuelle requise.

`r2bewi deploy r2bewi` détecte le premier VG LVM disponible et crée un LV
`registry` monté sur `/var/lib/docker-registry`. L'entrée `/etc/fstab` est
ajoutée par UUID pour persister le montage au reboot.

**Taille par défaut : 256 Go.** Ajustable via `--registry-size` :

```bash
sudo r2bewi deploy r2bewi --registry-size 128G
sudo r2bewi deploy r2bewi --registry-size 1T
```

Formats acceptés : `256G`, `128g`, `1T`. Unité minimale : gigaoctet.

**Si l'espace libre est insuffisant**, le déploiement s'arrête avec un message explicite :

```
ERROR Espace insuffisant dans le VG 'ubuntu-vg' :
ERROR   Demandé : 400G  —  Disponible : 328.5G
ERROR   Réduire avec --registry-size (ex. --registry-size 328G)
```

**Si aucun VG LVM n'est présent**, le registry stocke sur la partition système (fallback silencieux).

**Idempotent** : si `/var/lib/docker-registry` est déjà monté, aucune action.

**État attendu sur r2bewi après le déploiement :**

| LV        | VG        | Taille  | Point de montage           |
|-----------|-----------|---------|----------------------------|
| ubuntu-lv | ubuntu-vg | 100 G   | `/`                        |
| registry  | ubuntu-vg | 256 G   | `/var/lib/docker-registry` |

```bash
# Vérifier l'espace libre disponible dans le VG avant de choisir --registry-size
sudo blkid /dev/ubuntu-vg/registry   # UUID du LV
sudo vgs                              # espace libre restant dans le VG
```

---

## 2c. VPN WireGuard (accès réseaux K8s depuis le SDK)

Le VPN donne accès aux réseaux internes K8s (`10.42.0.0/16` pods, `10.43.0.0/16` services).
Il tourne comme pod K8s sur le bastion — déployé automatiquement par `r2bewi enroll`.

**Initialiser le pod WireGuard :**

```bash
# Générer les clés serveur
wg genkey | tee /tmp/wg.key | wg pubkey > /tmp/wg.pub

# Créer le Secret K8s avec la config serveur
kubectl create secret generic wireguard-config -n vpn \
  --from-file=wg0.conf=/dev/stdin <<EOF
[Interface]
Address    = 10.8.0.1/24
ListenPort = 51820
PrivateKey = $(cat /tmp/wg.key)
PostUp   = iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o br0 -j MASQUERADE; iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o wg0 -j ACCEPT
PostDown = iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -o br0 -j MASQUERADE; iptables -D FORWARD -i wg0 -j ACCEPT; iptables -D FORWARD -o wg0 -j ACCEPT
EOF
```

**Ajouter un peer SDK :**

```bash
# Sur le SDK — générer les clés client
wg genkey | tee /tmp/sdk.key | wg pubkey > /tmp/sdk.pub

# Sur le bastion — éditer le Secret et ajouter le peer
kubectl edit secret wireguard-config -n vpn
# Ajouter dans wg0.conf :
# [Peer] # dev-lionel
# PublicKey  = <contenu de /tmp/sdk.pub>
# AllowedIPs = 10.8.0.2/32

# Redémarrer le pod pour appliquer
kubectl rollout restart deployment/wireguard-gateway -n vpn
```

**Config client SDK** (`/etc/wireguard/wg0.conf`) :

```ini
[Interface]
Address    = 10.8.0.2/24
PrivateKey = <contenu de /tmp/sdk.key>

[Peer]
PublicKey           = <contenu de /tmp/wg.pub>
Endpoint            = <bastion-ip-wifi>:51820
AllowedIPs          = 10.8.0.0/24, 10.42.0.0/16, 10.43.0.0/16
PersistentKeepalive = 25
```

```bash
sudo wg-quick up wg0    # activer le VPN sur le SDK
```

---

## 3. Installer K3s server

> Exécuter avec `sudo` depuis le compte `iobewi` (ou tout compte membre du groupe `sudoers`).

```bash
sudo r2bewi enroll r2bewi
```

**Ce qui se passe :**

| Phase | Action |
|---|---|
| Préflight | root + iobewi + curl + config.yaml présent |
| Installation | `curl get.k3s.io \| sh -s - server` |
| Attente | `kubectl get nodes` disponible (timeout 120s) |
| Validation | token + service actif + node Ready |
| Manifests | copie `/usr/share/r2bewi/manifests/` → `/var/lib/rancher/k3s/server/manifests/r2bewi/` |

**Vérifications :**

```bash
systemctl is-active k3s
k3s kubectl get nodes             # r2bewi   Ready   control-plane
cat /var/lib/rancher/k3s/server/node-token
```

**Idempotent :** si K3s est déjà installé et le token présent, la commande s'arrête proprement.

---

## 4. Connecter les agents au LAN robot

Avant d'enrôler un agent :

1. Brancher l'agent physiquement sur un port Ethernet du bastion
2. Vérifier qu'il obtient une adresse DHCP sur `192.168.82.0/24`

```bash
cat /var/lib/misc/dnsmasq.leases
dig rpibewi-01.r2bewi.internal @127.0.0.1
```

---

## 5. Initialiser un agent

```bash
sudo r2bewi init r2arm01 --kind agent --ip 192.168.82.101
```

Génère les fichiers dans `/etc/r2bewi/nodes/r2arm01/` :

```
k3s-config.yaml    ← server_url + token (__TOKEN__ sera substitué à l'enrôlement)
registries.yaml    ← miroirs de registres
node-profile.yaml  ← profil matériel à remplir avant l'enrôlement
```

Remplir le profil matériel du nœud (voir [labels.md](labels.md)) :

```bash
nano /etc/r2bewi/nodes/r2arm01/node-profile.yaml
```

---

## 6. Valider la configuration de l'agent

```bash
sudo r2bewi validate r2arm01
```

Vérifie tous les fichiers présents dans `/etc/r2bewi/nodes/r2arm01/` :

```
  ✓  k3s-config.yaml
  ✓  node-profile.yaml
  ✓  registries.yaml
```

Pour valider un fichier spécifique :

```bash
sudo r2bewi validate r2arm01 --file node-profile.yaml
```

Visualiser les labels qui seront effectivement appliqués depuis le profil opérateur :

```bash
sudo r2bewi render-labels r2arm01
```

`render-labels` permet de visualiser les labels effectivement dérivés du profil opérateur avant application. C'est la commande de revue à utiliser après avoir rempli `node-profile.yaml`.

**Flux nominal complet :**

```bash
# 1. Remplir le profil
nano /etc/r2bewi/nodes/r2arm01/node-profile.yaml

# 2. Vérifier le profil
sudo r2bewi validate r2arm01
sudo r2bewi render-labels r2arm01

# 3. Déployer et enrôler
sudo r2bewi deploy r2arm01 --ip 192.168.82.101
sudo r2bewi enroll r2arm01 --ip 192.168.82.101
```

La validation est également exécutée automatiquement par `deploy`, `enroll` et `update` — une configuration invalide bloque le workflow.

---

## 7. Déployer la configuration de l'agent

```bash
sudo r2bewi deploy r2arm01 --ip 192.168.82.101
```

Effectue en SSH : hostname, swap, cloud-init désactivé, fichiers K3s.

Avec un utilisateur SSH différent du défaut (`iobewi`) :

```bash
sudo r2bewi deploy r2arm01 --ip 192.168.82.101 --ssh-user ubuntu
```

---

## 8. Enrôler l'agent

> Exécuter avec `sudo` depuis le compte `iobewi` (ou tout compte membre du groupe `sudoers`).

```bash
sudo r2bewi enroll r2arm01 --ip 192.168.82.101
```

Premier enrôlement avec un user d'usine (ex. `ubuntu`) :

```bash
sudo r2bewi enroll r2arm01 --ip 192.168.82.101 --bootstrap-user ubuntu
```

Agent NVIDIA (Jetson) :

```bash
sudo r2bewi enroll r2arm01 --ip 192.168.82.101 --bootstrap-user ubuntu --nvidia
```

**Ce qui se passe :**

| Phase | Action |
|---|---|
| Préflight local | root + iobewi + ssh + token K3s présent |
| Création user iobewi | `ssh-copy-id` vers bootstrap_user (1 seule fois), création `iobewi` si absent |
| Confiance SSH | clé publique iobewi installée sur l'agent |
| Préflight distant | SSH joignable + sudo + curl (installé si absent) + nvidia si requis |
| Idempotence | nœud déjà dans le cluster → mise à jour labels et sortie |
| Fichiers K3s | push `config.yaml` (token substitué) + `registries.yaml` (+ containerd NVIDIA si `--nvidia`) |
| Installation | `curl get.k3s.io \| sh -s - agent` via SSH |
| Attente | node Ready dans le cluster (timeout 90s) |
| Labels | `node-role.kubernetes.io/worker=worker` |

**Vérifications :**

```bash
k3s kubectl get nodes             # r2bewi + r2arm01   Ready
k3s kubectl get nodes --show-labels
```

---

## 9. Ajouter des agents supplémentaires

Répéter les étapes 5 à 7 avec un hostname distinct pour chaque agent :

```bash
sudo r2bewi init r2arm02 --kind agent --ip 192.168.82.102
sudo r2bewi deploy r2arm02 --ip 192.168.82.102
sudo r2bewi enroll r2arm02 --ip 192.168.82.102
```

---

## 10. Labels K3s

### Label automatique

À chaque enrôlement, r2bewi pose automatiquement :

```
node-role.kubernetes.io/worker=worker
```

Ce label est toujours appliqué — il n'est pas à définir manuellement.

### Labels personnalisés

**Source de vérité recommandée : `node-profile.yaml`**

Les labels sont déclarés dans `/etc/r2bewi/nodes/<hostname>/node-profile.yaml` sous les clés `compute:` et `device:` :

```yaml
compute:
  accelerator: nvidia
  class: embedded
  realtime: "false"
device:
  camera: stereo
  imu: integrated-camera
```

`r2bewi` traduit ce profil en labels Kubernetes `r2bewi.io/*` lors de l'enrôlement et de la mise à jour.
Visualiser les labels avant application :

```bash
sudo r2bewi render-labels r2arm01
```

> **Compatibilité legacy :** il est aussi possible de définir les labels directement dans la section
> `node-label` de `k3s-config.yaml`. Ce mode est conservé pour compatibilité mais `node-profile.yaml`
> est la source de vérité. En cas de conflit, `node-profile.yaml` a la priorité.

La convention de nommage, les familles de labels et les valeurs autorisées sont définies dans [labels.md](labels.md).

### Mettre à jour les labels d'un nœud

Modifier `node-profile.yaml`, puis :

```bash
sudo r2bewi update r2arm01
```

Applique tous les labels avec `--overwrite`. `node-role.kubernetes.io/worker=worker` est toujours réappliqué.

---

## 11. Vérifier l'état

```bash
sudo r2bewi status r2bewi                            # server
sudo r2bewi status r2arm01 --ip 192.168.82.101       # agent
```

---

## 12. Désinstaller

```bash
# Server
sudo r2bewi uninstall r2bewi

# Agent
sudo r2bewi uninstall r2arm01 --ip 192.168.82.101
```

**Ce que fait `uninstall` :**

| Étape (server) | Action |
|---|---|
| K3s | `k3s-uninstall.sh` |
| Fichiers gérés | restauration depuis sauvegarde si disponible, sinon suppression |
| systemd-resolved | retrait de `DNSStubListener=no`, restart |

| Étape (agent) | Action |
|---|---|
| K3s agent | `k3s-agent-uninstall.sh` via SSH |
| Fichiers distants | suppression `/etc/rancher/k3s/` sur l'agent |
| Cluster | `kubectl delete node <hostname>` |
| DNS | suppression entrée dans `/etc/dnsmasq.d/r2bewi-nodes.conf` + reload |

---

## Sauvegardes automatiques

Avant toute écriture de fichier système, `deploy` sauvegarde la version existante :

```
/var/lib/r2bewi/backup/
  manifest.json
  etc/netplan/50-r2bewi.yaml.20250101-120000
  etc/systemd/resolved.conf.20250101-120001
  ...
```

`uninstall` restaure automatiquement ces sauvegardes.

---

## Invariants critiques et non-régression

Les invariants ci-dessous couvrent les zones à risque identifiées dans le code. Toute modification des modules concernés doit s'assurer qu'ils sont préservés.

| Invariant | Module | Vérification |
|---|---|---|
| `_configure_resolved` (deploy) et `_restore_systemd_resolved` (uninstall) doivent rester en miroir | `deploy.py`, `uninstall.py` | Tester `deploy` puis `uninstall` : `/etc/systemd/resolved.conf` doit retrouver son état initial |
| La règle NAT MASQUERADE doit utiliser l'interface bridge lue depuis `dnsmasq.conf`, jamais `br0` en dur | `deploy.py` | `r2bewi deploy` avec `interface=br-lan` dans `dnsmasq.conf` → vérifier `iptables -t nat -L` |
| `push_file` doit survivre à des chemins contenant des espaces ou des apostrophes | `subprocess_utils.py` | Test unitaire `test_subprocess_utils.py::TestPushFile` |
| La clé publique SSH dans `create_iobewi_on_agent` doit être transportée via base64, sans interpolation directe dans le script shell | `iobewi_setup.py` | Test unitaire `test_iobewi_setup.py::TestCreateIobewi` |
| `ssh_user` passé à `deploy`, `enroll`, `status`, `uninstall` doit atteindre `ssh_target()` sans être écrasé par `"iobewi"` | `deploy.py`, `enroll.py`, `status.py`, `uninstall.py` | Tests `TestDispatch` + `TestUninstallSshUser` dans `test_cli.py` |
| `archive_directory` doit être appelé avant toute suppression dans `/etc/netplan/` et `/etc/dnsmasq.d/` | `deploy.py` | Inspecter `_apply_files_local` après toute modification de la logique de fichiers |

---

## Limites connues

| Limite | Détail |
|---|---|
| Agents DHCP uniquement | Pas de configuration IP statique agent |
| PSK Wi-Fi en clair | Le mot de passe Wi-Fi est en clair dans `netplan.yaml` — restreindre les droits fichier (0640) |
| Idempotence agent partielle | Un agent partiellement installé (K3s installé mais pas `Ready`) peut nécessiter une intervention manuelle |
| Upgrade K3s | Procédure d'upgrade K3s non encore formalisée |
