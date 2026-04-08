# Catalogue officiel des labels K3s — R2BEWI v1

Ce document définit la convention de labellisation des nœuds du cluster R2BEWI.

L'objectif est de décrire, de manière stable et exploitable par Kubernetes :

* ses ressources de calcul ;
* les équipements effectivement intégrés au nœud.

**La source de vérité est l'opérateur / installateur.**
Les labels ne sont pas découverts automatiquement.
Ils sont déclarés en fonction de l'intégration matérielle réelle du robot.

Le catalogue est également disponible en format machine-readable dans [`bootstrap/src/core/catalog/labels.yaml`](../bootstrap/src/core/catalog/labels.yaml),
utilisé par les outils de validation et la CLI.

---

## Namespace

Tous les labels custom utilisent le préfixe :

```text
r2bewi.io/
```

Ce namespace évite les collisions avec les labels système Kubernetes.

---

## Principes de normalisation

### 1. Un label décrit une seule nature d'information

Les labels sont répartis en familles distinctes :

| Famille | Clé / préfixe | Obligatoire | Description |
|---|---|---|---|
| Ressources de calcul | `r2bewi.io/compute.*` | oui | Environnement d'exécution déclaré |
| Équipements | `r2bewi.io/device.*` | non | Équipements réellement portés par le nœud |

En pratique, un nœud R2BEWI est décrit par son environnement d'exécution déclaré (`compute.*`) et les équipements effectivement intégrés (`device.*`).

> **Note :** l'architecture CPU (`arm64`, `amd64`) et l'OS sont déjà posés automatiquement par K3s via `kubernetes.io/arch` et `kubernetes.io/os`. Il n'est pas nécessaire de les redéclarer.

### 2. L'opérateur déclare la réalité terrain

Les labels `device.*` et `compute.*` décrivent l'intégration effectivement déclarée pour le nœud,
et non des possibilités génériques liées à la plateforme.

### 3. Nommage canonique

Les clés et valeurs doivent respecter les règles suivantes :

* minuscules uniquement ;
* caractères ASCII ;
* séparateur `-` pour les noms composés ;
* pas d'espaces ;
* pas de majuscules ;
* pas d'abréviations ambiguës.

### 4. Une même notion ne doit exister qu'à un seul endroit

Exemple :

* l'accélération GPU se décrit via `compute.accelerator=nvidia`
* elle ne doit pas être répétée ailleurs sous une autre forme

### 5. Les labels `device.*` décrivent des familles d'équipements

Le modèle retenu est :

```text
r2bewi.io/device.<famille>=<variante>
```

Exemples :

```text
r2bewi.io/device.camera=stereo
r2bewi.io/device.imu=global
r2bewi.io/device.range=ultrasonic
```

---

## Label automatique

Ce label peut être posé automatiquement par `r2bewi enroll` sur les agents.
Il relève des conventions Kubernetes d'exploitation et ne fait pas partie du catalogue métier R2BEWI.
Il ne doit pas être défini manuellement :

```text
node-role.kubernetes.io/worker
```

---

## 1. Ressources de calcul

### `r2bewi.io/compute.accelerator`

Accélération matérielle principale disponible pour les workloads.

| Valeur | Description |
|---|---|
| `none` | Pas d'accélération spécifique |
| `nvidia` | GPU NVIDIA disponible |
| `intel` | GPU / accélération Intel disponible |

### `r2bewi.io/compute.class`

Classe générale de calcul du nœud.

| Valeur | Description |
|---|---|
| `micro` | Calcul embarqué très léger |
| `embedded` | Calcul embarqué standard |
| `general` | Calcul généraliste |
| `high` | Calcul renforcé / intensif |

Cette classification est une convention opérationnelle interne à R2BEWI.
Elle sert au placement de workloads et à la description d'inventaire, mais ne constitue pas une mesure normalisée de performance.

### `r2bewi.io/compute.realtime`

Indique si le nœud est intégré pour héberger des workloads à contrainte temps réel ou pseudo temps réel.

| Valeur | Description |
|---|---|
| `true` | Usage temps réel / contrôle bas niveau prévu |
| `false` | Pas d'usage temps réel prévu |

---

## 2. Catalogue des équipements

Les labels `device.*` décrivent les équipements effectivement intégrés au nœud.

```text
r2bewi.io/device.<famille>=<variante>
```

**Règle importante :** un label Kubernetes ne peut exister qu'une seule fois par clé.
Un nœud ne peut donc avoir qu'une seule valeur par famille dans ce modèle v1.
Si plusieurs équipements d'une même famille doivent être décrits, une extension v2 introduira une convention complémentaire.

**Convention d'inventaire :** les labels `device.*` sont déclaratifs.
Ils ne sont posés que lorsqu'un équipement de la famille considérée est effectivement porté par le nœud.

L'absence d'un label `device.*` signifie qu'aucun équipement de cette famille n'est déclaré pour ce nœud dans l'inventaire R2BEWI.
L'opérateur a la responsabilité de poser tous les labels pertinents ; ce qui n'est pas posé est réputé absent de l'inventaire R2BEWI.

### Récapitulatif des familles disponibles

| Famille | Clé | Équipement décrit |
|---|---|---|
| Caméra | `r2bewi.io/device.camera` | Système de caméra principal |
| IMU | `r2bewi.io/device.imu` | Centrale inertielle |
| LiDAR | `r2bewi.io/device.lidar` | Télémétrie laser |
| Télémétrie courte portée | `r2bewi.io/device.range` | Ultrason, infrarouge, ToF |
| Moteur | `r2bewi.io/device.motor` | Commande moteur principale |
| Codeur | `r2bewi.io/device.encoder` | Retour position / odométrie |
| GNSS | `r2bewi.io/device.gnss` | Localisation satellite |
| Audio | `r2bewi.io/device.audio` | Entrée / sortie audio |
| Affichage | `r2bewi.io/device.display` | Sortie vidéo / afficheur |

### `r2bewi.io/device.camera`

| Valeur | Description |
|---|---|
| `mono` | Caméra monoculaire |
| `stereo` | Caméra stéréo |
| `rgbd` | Caméra RGB-D |
| `fisheye` | Caméra fisheye |
| `tracking` | Caméra orientée suivi / tracking |

### `r2bewi.io/device.imu`

| Valeur | Description |
|---|---|
| `global` | IMU principale du robot |
| `local` | IMU locale à un sous-ensemble mécanique |
| `integrated-camera` | IMU intégrée à un module caméra |
| `integrated-lidar` | IMU intégrée à un module LiDAR |

### `r2bewi.io/device.lidar`

| Valeur | Description |
|---|---|
| `2d` | LiDAR 2D |
| `3d` | LiDAR 3D |
| `solid-state` | LiDAR solid-state |

### `r2bewi.io/device.range`

| Valeur | Description |
|---|---|
| `ultrasonic` | Télémétrie ultrason |
| `infrared` | Télémétrie infrarouge |
| `tof` | Time-of-Flight |

### `r2bewi.io/device.motor`

| Valeur | Description |
|---|---|
| `dc` | Commande moteur DC |
| `bldc` | Commande moteur brushless |
| `servo` | Commande servo |
| `stepper` | Commande moteur pas à pas |

### `r2bewi.io/device.encoder`

| Valeur | Description |
|---|---|
| `incremental` | Codeur incrémental |
| `absolute` | Codeur absolu |
| `multi-turn` | Codeur absolu multi-tour |

### `r2bewi.io/device.gnss`

| Valeur | Description |
|---|---|
| `standard` | GNSS standard |
| `rtk` | GNSS RTK |

### `r2bewi.io/device.audio`

| Valeur | Description |
|---|---|
| `microphone` | Entrée microphone |
| `speaker` | Sortie haut-parleur |
| `duplex` | Entrée/sortie audio |

### `r2bewi.io/device.display`

| Valeur | Description |
|---|---|
| `hdmi` | Affichage HDMI |
| `dsi` | Affichage DSI |
| `oled` | Petit afficheur OLED |
| `lcd` | Afficheur LCD |

---

## 3. Exemples de profils de nœuds

### Jetson Xavier NX avec caméra stéréo et IMU intégrée

```yaml
compute:
  accelerator: nvidia
  class: embedded
  realtime: "false"
device:
  camera: stereo
  imu: integrated-camera
```

### Raspberry Pi 5 avec IMU, ultrason et commande moteur

```yaml
compute:
  accelerator: none
  class: embedded
  realtime: "true"
device:
  imu: global
  range: ultrasonic
  motor: bldc
  encoder: incremental
```

### Bastion x86 généraliste

```yaml
compute:
  accelerator: none
  class: general
  realtime: "false"
device:
  display: hdmi
```

---

## 4. Utilisation dans les manifests

### nodeSelector (simple)

```yaml
spec:
  nodeSelector:
    r2bewi.io/compute.accelerator: nvidia
    r2bewi.io/device.camera: stereo
```

### nodeAffinity (avancé)

```yaml
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: r2bewi.io/device.range
                operator: In
                values: [ultrasonic, tof]
              - key: r2bewi.io/compute.realtime
                operator: In
                values: ["true"]
```

---

## 5. Vérification

```bash
# Voir les labels d'un nœud
k3s kubectl get node jetbewi-01 --show-labels

# Filtrer les nœuds avec accélération NVIDIA
k3s kubectl get nodes -l r2bewi.io/compute.accelerator=nvidia

# Filtrer les nœuds avec caméra stéréo
k3s kubectl get nodes -l r2bewi.io/device.camera=stereo

# Filtrer les nœuds temps réel
k3s kubectl get nodes -l r2bewi.io/compute.realtime=true
```

---

## 6. Limites connues et évolutions prévues

Cette simplicité garantit la lisibilité, la maintenabilité et la stabilité de la convention.

| Limite v1 | Impact | Prévu en v2 |
|---|---|---|
| Une seule valeur par famille `device.*` | Impossible de décrire deux caméras | Convention multi-instances |
| Pas de position physique | Impossible de distinguer `front` / `rear` | Attribut de position |
| Pas de priorité d'équipement | Pas de distinction principal / secondaire | Attribut de rang |
| Pas de description des bus matériels | Pas d'info USB / I2C / SPI | Extension bus |
| Pas d'auto-discovery | L'opérateur déclare tout manuellement | Hors scope intentionnel |
