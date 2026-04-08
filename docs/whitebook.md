## 1. Page de couverture

**R2BEWI — Vers une infrastructure explicite pour les systèmes robotiques distribués**

*Structurer la séparation des contraintes physiques et logicielles pour des déploiements reproductibles, maîtrisés et opérables.*

**Auteur :** Lionel Orcil
**Organisation :** R2BEWI
**Date :** Avril 2026

---

## 2. Résumé exécutif

### Problème abordé

Les systèmes robotiques distribués combinent des contraintes hétérogènes : interaction matérielle (bus, capteurs, actionneurs), exigences de temps réel, et besoins de déploiement et de supervision multi-nœuds.

Si des outils matures existent — ROS 2 pour l’applicatif, Kubernetes/K3s pour l’orchestration, DDS/Zenoh pour la communication — leur articulation reste complexe. En pratique, la séparation entre fonctions temps réel strictes et fonctions distribuées est souvent implicite, rendant les systèmes difficiles à reproduire, à diagnostiquer et à faire évoluer.

### Principales conclusions

* Le problème central n’est pas un manque d’outils, mais un manque de **structuration explicite** de leur intégration.
* Les environnements conteneurisés et orchestrés sont adaptés au **temps réel souple**, mais pas aux boucles critiques dépendantes du matériel.
* La séparation entre **hard real-time** et **soft real-time** est déjà présente dans les systèmes, mais rarement formalisée.
* Le réseau est le point de fragilité principal, où se cristallisent les effets de topologie, de latence et de configuration.

R2BEWI propose de structurer cette réalité autour de trois axes :

* une description déclarative des capacités matérielles (labels `r2bewi.io/*`) ;
* un placement explicite des charges de travail via l’orchestrateur ;
* une gestion maîtrisée des communications (ROS 2, Zenoh, Zenoh-Pico).

### Recommandations clés

* **Isoler les fonctions temps réel strictes** au plus proche du matériel (firmware, implémentation embarquée légère de Zenoh adaptée aux microcontrôleurs), hors de la couche orchestrée.
* **Utiliser l’orchestration pour les fonctions distribuées**, en assumant un modèle de temps réel souple.
* **Rendre explicites les capacités et contraintes** des nœuds via des modèles déclaratifs et des labels.
* **Privilégier des communications contrôlées** (routage explicite, unicast) pour maîtriser les environnements réseau distribués.
* **Outiller l’administration de l’infrastructure bas niveau via un CLI idempotent**, afin de réduire la dépendance aux configurations implicites.

Cette approche ne réduit pas la complexité intrinsèque des systèmes robotiques, mais permet de la rendre **lisible, reproductible et maîtrisable**.

---

## 3. Introduction

Les systèmes robotiques modernes reposent sur une diversité de composants matériels, chacun répondant à des contraintes fonctionnelles spécifiques. Les cartes ARM assurent l'interfaçage bas niveau avec le matériel — bus I2C, SPI, CAN — là où les accélérateurs GPU et TPU prennent en charge les traitements de perception et d'intelligence artificielle. Les architectures x86, quant à elles, sont dédiées à la supervision, à l'orchestration et au calcul généraliste.

Cette hétérogénéité n'est pas une exception : elle est constitutive des systèmes robotiques avancés. Elle impose de concevoir des architectures distribuées capables de faire coopérer des machines aux capacités très différentes, dans des environnements souvent contraints.

ROS 2 s'est imposé, dans la recherche comme dans les systèmes ouverts, comme le middleware de référence pour le développement d'applications robotiques modulaires. Son modèle de communication par topics et services permet de découpler efficacement les composants du système.

Cependant, ROS 2 ne fournit pas de réponse complète aux contraintes de temps réel strict (hard real-time) : bien que des mécanismes de QoS existent, le comportement dépend fortement de l’environnement d’exécution (OS, réseau, charge système). En pratique, les boucles critiques (contrôle moteur, acquisition capteurs) sont souvent traitées en dehors de ROS 2, au plus proche du matériel.

Pour autant, ROS 2 ne traite pas la question de l'infrastructure : il ne fournit ni mécanisme de déploiement, ni isolation des dépendances, ni contrôle de l'exécution à l'échelle d'un système distribué.

La conteneurisation, associée à des orchestrateurs légers, constitue une réponse pertinente à ces limitations. Elle permet d'isoler les environnements d'exécution et de structurer le déploiement des applications. Mais elle introduit en contrepartie une complexité opérationnelle réelle — configuration, gestion du réseau, supervision — qui devient vite difficile à maîtriser dès lors que plusieurs machines sont impliquées.

Le réseau est précisément le point où cette complexité se cristallise. Dans un réseau local simple, les mécanismes de communication ROS 2 fonctionnent de manière transparente. Dans une architecture distribuée impliquant plusieurs machines, des sous-réseaux ou des liaisons intermittentes, leur comportement devient difficile à anticiper et à maîtriser de manière déterministe.

Ces difficultés convergent vers un enjeu central : concevoir une infrastructure capable d'intégrer de manière cohérente des composants logiciels hétérogènes, des contraintes matérielles variables et des conditions réseau dégradées, en particulier dans des contextes embarqués, hors ligne ou faiblement connectés.

Ce document analyse ces enjeux et propose une approche structurée pour la conception et l'exploitation de systèmes robotiques distribués. L’analyse s’articule autour de trois axes principaux : les contraintes matérielles et logicielles, les stratégies de déploiement par conteneurisation et la gestion du réseau en environnement distribué. Elle conduit à une définition structurée du problème, préalable à la proposition d’une approche adaptée.

---

## 4. État des lieux / Analyse

### 4.1 ROS 2 : un middleware structurant mais centré sur l’application

ROS 2 constitue aujourd’hui un socle solide pour le développement d’applications robotiques distribuées. Son modèle de communication basé sur des topics, services et actions permet de découpler efficacement les composants et de structurer des systèmes modulaires.

L’écosystème propose également des outils matures pour le développement, la simulation et le diagnostic. Les middlewares DDS sous-jacents, tels que Cyclone DDS ou Fast DDS, offrent des mécanismes avancés de configuration, notamment en matière de qualité de service (QoS), de découverte et de transport.

Cependant, ROS 2 reste centré sur la couche applicative. Il ne fournit pas de solution intégrée pour le déploiement multi-nœuds, la gestion des dépendances, la reproductibilité des environnements ou le contrôle explicite du placement des composants.

Certaines approches tentent de combler ces lacunes, comme l'utilisation de systèmes de lancement avancés, des outils comme robot_upstart pour le déploiement embarqué, ou encore des intégrations avec Kubernetes (ros2-k8s, ROSbloX). Ces solutions apportent des réponses partielles mais restent souvent limitées à un aspect spécifique du problème.

---

### 4.2 Conteneurisation et orchestration : puissance et complexité

La conteneurisation permet d’isoler les environnements logiciels et de garantir une meilleure reproductibilité des applications. Associée à un orchestrateur comme Kubernetes ou K3s, elle introduit des capacités avancées de gestion du cycle de vie, de déploiement déclaratif et d’exploitation des ressources.

Ces mécanismes sont particulièrement adaptés à des systèmes distribués. Ils permettent notamment d’automatiser le redémarrage des services, de gérer les ressources disponibles et de structurer l’infrastructure.

Cependant, leur adoption dans un contexte robotique introduit plusieurs défis :

* la complexité de configuration et d’exploitation ;
* la gestion des périphériques matériels (bus, GPU, interfaces spécifiques) ;
* l’adéquation avec des contraintes de temps réel ;
* la nécessité de définir explicitement des stratégies de placement adaptées.

Un point structurant concerne précisément le temps réel : les environnements conteneurisés et orchestrés ne fournissent pas de garanties fortes en matière de latence ou de déterminisme. Ils sont adaptés à des charges en temps réel souple, mais pas à des boucles critiques dépendant directement du matériel.

Cela conduit, dans la pratique, à une séparation implicite des responsabilités :

* une couche bas niveau dédiée aux fonctions temps réel strictes ;
* une couche orchestrée dédiée aux fonctions applicatives et distribuées.

Kubernetes fournit des outils comme les politiques d’affinité et de placement, mais ne propose pas de modèle spécifique pour exprimer les contraintes matérielles propres à la robotique.

---

### 4.3 Communication distribuée : entre puissance et maîtrise

Le modèle de communication de ROS 2 repose sur DDS, qui offre des fonctionnalités avancées adaptées à des systèmes distribués. Les mécanismes de découverte automatique et de gestion de la qualité de service permettent une grande flexibilité.

Dans des environnements contrôlés, ce modèle fonctionne efficacement.

Cependant, dans des architectures distribuées réelles, il présente plusieurs limites :

* dépendance à la topologie réseau ;
* trafic multicast difficile à maîtriser ;
* complexité de configuration des profils DDS ;
* difficultés à traverser des sous-réseaux, du NAT ou des VPN.

Des solutions existent pour atténuer ces contraintes, notamment via la configuration des middlewares DDS ou l’utilisation de solutions alternatives comme Zenoh, qui propose un modèle basé sur le routage explicite et des communications unicast.

Néanmoins, ces approches nécessitent des choix d’architecture structurants et restent complexes à intégrer dans un système global.

---

## 5. Définition du problème

L’analyse des approches existantes met en évidence un constat récurrent : les briques nécessaires à la construction d’un système robotique distribué sont disponibles, mais leur articulation reste difficile.

ROS 2 fournit un modèle de communication robuste au niveau applicatif, la conteneurisation permet d’isoler les environnements, et les orchestrateurs facilitent la gestion des ressources. Des solutions existent également pour adapter les communications aux contraintes réseau.

Cependant, ces outils reposent sur des modèles différents et ont été conçus indépendamment les uns des autres. Leur combinaison nécessite de faire des choix d’architecture implicites, souvent spécifiques à chaque projet.

Un point critique concerne la gestion du temps réel :

* les fonctions critiques sont généralement traitées en dehors des environnements orchestrés ;
* cette séparation est rarement formalisée dans l’architecture globale ;
* elle introduit une complexité supplémentaire dans l’intégration du système.

Cette situation conduit à plusieurs difficultés :

* l’absence d’un modèle unifié pour décrire les capacités matérielles des nœuds ;
* des stratégies de déploiement et de placement peu explicites ;
* une gestion du réseau dépendante du contexte et difficile à reproduire ;
* une séparation implicite et non formalisée entre temps réel strict et temps réel souple ;
* une forte dépendance à l’intégrateur.

En pratique, chaque système robotique distribué devient un assemblage spécifique, dont le fonctionnement repose autant sur des choix techniques que sur une connaissance implicite accumulée au fil du développement.

Le problème fondamental réside moins dans l’absence d’outils que dans la difficulté à structurer leur utilisation de manière explicite, reproductible et adaptée aux contraintes du terrain, y compris en ce qui concerne la séparation des responsabilités temps réel.

---

## 6. Solutions proposées

### 6.1 Une approche structurée de l’infrastructure robotique

Face aux limites identifiées, l’objectif n’est pas d’introduire de nouveaux outils, mais de structurer l’utilisation de ceux existants.

R2BEWI propose une approche cohérente de l’infrastructure robotique distribuée, fondée sur une idée centrale : rendre explicites les éléments qui sont habituellement implicites dans l’intégration des systèmes.

Ces principes sont indépendants de l’outil d’orchestration retenu : Kubernetes/K3s en constitue une instanciation pratique, mais le modèle (capacités déclaratives, placement explicite, flux contrôlés) reste valable sans lui.

Cette approche repose sur trois principes :

* la description explicite des capacités matérielles ;
* le pilotage déterministe du placement des charges de travail ;
* la maîtrise des communications dans des environnements distribués.

---

### 6.2 Un modèle unifié basé sur les capacités matérielles

Le premier élément structurant consiste à introduire un modèle explicite de description des nœuds.

Chaque machine est caractérisée par un profil déclaratif (fichier YAML) décrivant ses ressources de calcul et ses capacités matérielles (capteurs, actionneurs, GPU, interfaces CAN/I2C, etc.). Ce profil est traduit en labels Kubernetes sous un espace de nommage dédié (par exemple `r2bewi.io/*`).

Ces labels sont des labels Kubernetes standards, validés par un catalogue (schéma) afin de garantir leur cohérence. Ils sont ensuite utilisés par l’orchestrateur pour le placement (`nodeSelector`, `nodeAffinity`).

Ce modèle permet de passer d’un placement implicite des applications à un placement piloté par les capacités réelles du système, de manière explicite et reproductible.

---

### 6.3 Orchestration pilotée et reproductible

Sur cette base, l’orchestration ne repose plus sur des conventions implicites, mais sur des règles explicites.

R2BEWI s’appuie sur un orchestrateur léger, typiquement K3s, afin de bénéficier des primitives Kubernetes tout en conservant une empreinte adaptée à l’embarqué.

Les charges de travail sont déployées sous forme de manifestes Kubernetes (Deployments, DaemonSets) intégrant des contraintes de placement basées sur les labels `r2bewi.io/*`.

Cela garantit :

* un placement cohérent avec le matériel disponible ;
* une meilleure reproductibilité des déploiements ;
* une réduction des erreurs liées à la configuration manuelle.

Les stratégies de placement deviennent ainsi déclaratives et versionnables.

---

### 6.4 Une approche maîtrisée de la communication

La communication est traitée comme un élément d’architecture à part entière.

R2BEWI privilégie une approche basée sur un routage explicite des flux, en s’appuyant sur Zenoh pour les déploiements distribués, tout en restant compatible avec DDS pour des environnements locaux simples.

Concrètement, cela se traduit par :

* l’utilisation de ponts (bridges) entre ROS 2 et Zenoh lorsque nécessaire ;
* la réduction du multicast au profit de communications unicast routées ;
* la définition explicite des chemins de communication entre nœuds.

Cette approche permet de limiter le trafic inutile, de s’adapter à des architectures réseau segmentées (sous-réseaux, VPN) et d’améliorer la prévisibilité du système.

---

### 6.5 Un outil opérateur pour structurer l’ensemble

Afin de rendre cette approche opérationnelle, R2BEWI s’appuie sur un outil en ligne de commande qui agit comme point d’entrée unique.

Ce CLI génère et applique les configurations nécessaires à l’infrastructure bas niveau : profils de nœuds, labels Kubernetes, configurations réseau et services d’infrastructure (dnsmasq, NAT/bridge, chrony, registry OCI, WireGuard). Il s’appuie sur les outils standards (kubectl, SSH, gestion de configuration) plutôt que de les remplacer.

Il n’a pas vocation à gérer le contenu fonctionnel de la pile applicative. Les stacks ROS 2, Zenoh et les composants métiers sont déployés au niveau des conteneurs et de leurs manifestes, non par le CLI lui-même.

Les artefacts produits (manifestes, profils) sont **inspectables et versionnables** : le CLI vise à exposer les décisions (placement, contraintes) plutôt qu’à les masquer.

Il permet notamment de :

* initialiser un nœud (profil matériel et réseau) ;
* déployer l’infrastructure bas niveau (K3s, services réseau, registry) ;
* enrôler de nouveaux nœuds dans le cluster ;
* mettre à jour les labels et les configurations d’infrastructure de manière idempotente.

L’objectif est de réduire la dépendance à l’intégrateur sur la couche d’administration bas niveau, en rendant les opérations d’infrastructure explicites, reproductibles et automatisables.

---

### 6.6 Synthèse : correspondance problème → réponse

La proposition R2BEWI répond point par point aux difficultés identifiées en section 5.

| Difficulté (§5)                        | Réponse R2BEWI (§6)                                                                        |
| -------------------------------------- | ------------------------------------------------------------------------------------------ |
| Absence de modèle unifié               | Profils YAML + labels Kubernetes `r2bewi.io/*` validés                                     |
| Placement implicite                    | `nodeSelector` / `nodeAffinity` basés sur labels                                           |
| Réseau dépendant du contexte           | Zenoh + bridges ROS 2 ↔ Zenoh, routage explicite                                           |
| Dépendance à l’intégrateur             | CLI idempotent pour l’administration bas niveau (génération + application via kubectl/SSH) |
| Séparation implicite hard RT / soft RT | Cloisonnement explicite : Zenoh-Pico (hard RT) + orchestration K3s (soft RT)               |

Cette correspondance explicite clôt la boucle entre l’analyse et la proposition, et rend l’approche directement opérationnelle.

---

### 6.7 Périmètre, modes dégradés et invariants

L’approche proposée ne supprime pas la complexité intrinsèque des systèmes distribués ; elle la rend explicite et structurée. Elle repose sur des choix d’architecture assumés, qu’il est nécessaire de rendre explicites.

#### Périmètre d’application

R2BEWI cible principalement des systèmes compatibles avec des contraintes de temps réel souple.

Dans ce modèle :

* les fonctions critiques à forte contrainte temporelle (boucles de contrôle, sécurité) sont gérées au niveau firmware ou systèmes dédiés ;
* la couche d’orchestration (conteneurs, K3s) opère en soft real-time, avec des garanties limitées en latence et en déterminisme.

Ce positionnement est un choix architectural : il permet de bénéficier des outils d’orchestration modernes sans chercher à leur faire porter des contraintes pour lesquelles ils ne sont pas conçus.

#### Modes dégradés

L’infrastructure est conçue pour conserver un comportement compréhensible en conditions dégradées.

Plusieurs situations sont considérées :

* **fonctionnement local** : un nœud doit pouvoir exécuter ses fonctions essentielles sans dépendre du cluster ;
* **perte de la couche de communication distribuée (Zenoh indisponible)** : les communications locales ROS 2 restent fonctionnelles ;
* **perte d’un nœud** : les mécanismes d’orchestration assurent le redéploiement ou la reprise des services lorsque cela est possible ;
* **dégradation réseau** : les flux explicitement définis permettent d’identifier et de limiter les impacts.

L’objectif n’est pas d’éliminer les défaillances, mais de garantir que leur effet reste maîtrisé et observable.

#### Limites et hypothèses

L’explicitation des capacités et des flux n’implique pas une maîtrise complète du comportement du système. Elle améliore la lisibilité, la reproductibilité et le diagnostic, mais ne supprime pas les effets liés aux conditions réelles d’exécution : latence réseau, jitter, contention des ressources.

Par ailleurs, le choix d’un socle Kubernetes introduit un modèle d’exécution spécifique, orienté vers des charges distribuées et tolérantes aux variations. Ce modèle peut entrer en tension avec certaines exigences de la robotique embarquée, notamment lorsque le couplage matériel est fort.

Enfin, la réduction de la dépendance à l’intégrateur ne signifie pas la disparition de l’expertise, mais sa transformation. L’effort se déplace vers des compétences en ingénierie système distribuée (orchestration, réseau, middleware), ce qui constitue une **montée en abstraction** plutôt qu’une simplification.

L’effort se déplace vers la définition explicite des contraintes, la compréhension des modèles sous-jacents et leur intégration cohérente.

#### Invariants système

Dans ce cadre, les invariants du système deviennent des propriétés comportementales observables :

* un nœud isolé du cluster doit pouvoir continuer à exécuter ses fonctions locales essentielles ;
* toute décision de placement doit être traçable et explicable à partir des contraintes déclarées ;
* les flux de communication doivent être explicitement définis et inspectables ;
* le déploiement et la reconfiguration du système doivent être reproductibles de manière déterministe à partir des descriptions déclaratives.

Ces invariants visent à garantir que le système reste opérable, compréhensible et prévisible, même en présence de conditions dégradées ou d’évolutions de l’infrastructure.

---

## 7. Étude de cas — Plateforme R2BEWI

### 7.1 Contexte et architecture cible

La plateforme R2BEWI illustre l’application concrète de l’approche proposée sur un système robotique réel.

Elle repose sur une architecture distribuée composée de trois types de nœuds :

* un nœud x86 assurant les fonctions de supervision, d’orchestration et de services réseau ;
* un nœud embarqué dédié au contrôle (interfaces CAN, I2C, capteurs, actionneurs) ;
* un nœud embarqué avec accélération GPU dédié à la perception et à l’inférence.

Le nœud x86 joue également un rôle de **gateway réseau** : il assure le routage entre interfaces, la translation d’adresses (NAT), la gestion du bridge (br0) et la distribution des adresses IP (DHCP) pour le réseau robot.

Ces nœuds sont interconnectés via un réseau local robot, potentiellement étendu par un accès distant sécurisé.

---

### 7.2 Description des nœuds

Chaque nœud est décrit via un profil déclaratif traduisant ses capacités matérielles.

Exemples :

* nœud contrôle : `r2bewi.io/device.motor=true`, `r2bewi.io/compute.class=embedded` ;
* nœud perception : `r2bewi.io/compute.accelerator=nvidia`, `r2bewi.io/device.camera=stereo` ;
* nœud supervision : `r2bewi.io/compute.class=general`.

Ces descriptions permettent un placement explicite des charges de travail.

---

### 7.3 Déploiement de l’infrastructure

Le déploiement est réalisé via le CLI R2BEWI depuis le nœud de supervision.

Les étapes principales sont :

* initialisation des profils de nœuds ;
* déploiement de K3s sur le nœud central ;
* enrôlement des nœuds embarqués ;
* application des labels Kubernetes ;
* déploiement des services d’infrastructure (DNS/DHCP via dnsmasq, gateway NAT/bridge, registry OCI locale, synchronisation temporelle via chrony, VPN WireGuard).

**Synchronisation temporelle.** La synchronisation des horloges est assurée par chrony sur l’ensemble des nœuds. Elle est essentielle pour la cohérence des timestamps ROS 2, des transformations (TF) et des journaux distribués.

**Registry OCI locale.** Une registry privée est déployée sur le réseau robot afin de permettre le déploiement d’images en environnement hors ligne ou faiblement connecté. Les images applicatives (ROS 2, Zenoh, etc.) y sont publiées et consommées par les nœuds.

**Accès distant.** L’accès au cluster est assuré via un VPN basé sur WireGuard, en mode pair-à-site, permettant aux machines de développement d’accéder au réseau robot de manière sécurisée.

**Identité d’administration.** Un utilisateur dédié (clé SSH contrôlée) est utilisé pour les opérations distantes du CLI, afin d’isoler les accès et de garantir la traçabilité des actions.

L’ensemble du processus est idempotent et reproductible.

---

### 7.4 Placement des charges de travail

Les applications ROS 2 sont déployées sous forme de conteneurs avec des contraintes explicites :

* les nœuds de contrôle sont placés sur les machines disposant d’interfaces matérielles ;
* les pipelines de perception sont placés sur les nœuds GPU ;
* les services de coordination sont exécutés sur le nœud x86.

Ce placement est défini par des règles déclaratives basées sur les labels.

---

### 7.5 Communication et réseau

La pile applicative déployée dans les conteneurs repose sur une combinaison de ROS 2, Zenoh et Zenoh-Pico, chacun occupant un rôle distinct :

* **ROS 2 (DDS)** est utilisé pour les communications locales non critiques et la structuration applicative ;
* **Zenoh** est utilisé pour les échanges distribués (multi-nœuds, sous-réseaux, VPN) via un routage explicite et des flux unicast ;
* **Zenoh-Pico** est utilisé pour les fonctions temps réel strictes (IMU, capteurs, gestion batterie), exécutées au plus proche du matériel ;
* des **bridges ROS 2 ↔ Zenoh** assurent l’interopérabilité entre les domaines local et distribué.

Cette pile de communication relève de la couche conteneurisée et de ses manifestes applicatifs. Le CLI intervient sur le socle d’infrastructure, mais n’installe ni n’administre directement les composants ROS 2 ou Zenoh.

Zenoh-Pico est une implémentation embarquée minimale de Zenoh, conçue pour fonctionner sans OS ou sur microcontrôleurs. Son empreinte et son modèle d’exécution le rendent adapté aux boucles temps réel strictes, contrairement aux composants conteneurisés.

Ce choix architectural est motivé : les boucles critiques ne sont pas exécutées dans des conteneurs orchestrés, car ceux-ci n’offrent pas de garanties de latence ni de déterminisme. Elles sont isolées dans des composants légers dédiés, tandis que la couche d’orchestration opère en temps réel souple — conformément au périmètre défini en §6.7.

Cette séparation permet de cloisonner explicitement les contraintes physiques du système des contraintes d’orchestration :

* les fonctions critiques restent déterministes et indépendantes du cluster ;
* la couche distribuée conserve sa flexibilité face aux variations réseau.

Cette configuration permet de maintenir des communications fonctionnelles même en cas de segmentation réseau, tout en conservant des propriétés temps réel sur les fonctions critiques.

---

### 7.6 Comportement en conditions dégradées

Plusieurs scénarios ont été considérés et observés :

* **perte du réseau** : les nœuds continuent à fonctionner localement ; les fonctions critiques restent actives car découplées de la couche distribuée ;
* **indisponibilité de la couche distribuée (Zenoh)** : les communications locales ROS 2 restent actives ; les données critiques continuent d’être produites/consommées localement ;
* **perte d’un nœud** : les mécanismes d’orchestration redéploient les services lorsque cela est possible ; les autres nœuds conservent leurs fonctions locales ;
* **dégradation réseau (latence/jitter)** : les flux explicitement définis permettent d’identifier rapidement les impacts ; les chemins critiques restent confinés localement.

Ces comportements illustrent les invariants définis en section 6 et montrent que le système reste opérable même en présence de défaillances partielles.

---

### 7.7 Retour d’expérience

Les observations suivantes sont issues d’un retour qualitatif sur des déploiements de la plateforme R2BEWI.

* **Temps de déploiement** : passage d’un provisionnement manuel (plusieurs heures, dépendant de scripts ad hoc) à un déploiement automatisé en moins de 20–30 minutes pour un cluster complet.
* **Compréhension du système** : les profils de nœuds et les labels rendent explicites les capacités et les contraintes, facilitant le diagnostic et les évolutions.
* **Erreurs de configuration** : diminution des erreurs liées aux placements implicites (mauvais nœud, dépendances manquantes), grâce aux contraintes déclaratives.

En contrepartie, l’approche nécessite une montée en compétence sur Kubernetes/K3s et sur les modèles de communication distribuée (Zenoh).

Ces éléments indiquent que l’approche R2BEWI ne réduit pas la complexité intrinsèque, mais améliore significativement sa lisibilité, sa reproductibilité et sa maîtrisabilité.

---

## 8. Conclusion

Les systèmes robotiques distribués ne souffrent pas d’un manque d’outils, mais d’un manque de structuration explicite dans leur intégration.

L’analyse a montré que les briques existantes — ROS 2, conteneurs, orchestrateurs, middlewares réseau — couvrent chacune une partie du problème, mais reposent sur des modèles hétérogènes.

Un point structurant est la séparation des contraintes : exigences physiques (temps réel, interaction matérielle) d’un côté, besoins de flexibilité (déploiement, distribution, supervision) de l’autre.

R2BEWI rend cette séparation explicite :

* une couche dédiée aux fonctions temps réel strictes, au plus proche du matériel ;
* une couche orchestrée, adaptée aux traitements distribués.

Complétée par un modèle déclaratif des capacités, un placement piloté et une communication maîtrisée, cette approche vise à rendre les systèmes compréhensibles, reproductibles et opérables.

R2BEWI ne constitue pas une nouvelle pile, mais un cadre d’intégration cohérent des outils existants.

À terme, il s’agit de décrire les systèmes robotiques par leurs contraintes et invariants, plutôt que comme des assemblages ad hoc — en rendant explicite ce qui était implicite.