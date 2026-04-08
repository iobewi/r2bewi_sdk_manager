REGISTRY_HOST  ?= registry.r2bewi.internal
REGISTRY_PORT  ?= 5000
IMAGE_TAG      ?= latest
MODULE          := $(shell pwd)
DOCKER           = docker compose -f $(MODULE)/docker/compose.yaml run --rm containers-build

REGISTRY       = $(REGISTRY_HOST):$(REGISTRY_PORT)
SERVICES       = ros-core motion perception

PLATFORM       ?= linux/arm64
ARM64_SVC      ?= ros-core
BUILDX_BUILDER ?= r2bewi-arm64

# kubectl pointe vers le cluster K3s via le VPN WireGuard (10.8.0.1:6443).
# Récupérer le kubeconfig une fois depuis le bastion :
#   scp iobewi@10.8.0.1:/etc/rancher/k3s/k3s.yaml ~/.kube/r2bewi.yaml
#   sed -i 's|https://127.0.0.1:6443|https://10.8.0.1:6443|' ~/.kube/r2bewi.yaml
KUBECONFIG     ?= $(HOME)/.kube/r2bewi.yaml
KUBECTL        ?= kubectl --kubeconfig=$(KUBECONFIG)

.PHONY: help shell docker-build build push clean test \
        buildx-setup build-arm64 \
        deploy-test logs-test clean-test

help:
	@echo ""
	@echo "R2BEWI — Containers"
	@echo ""
	@echo "  build             Build toutes les images R2BEWI (x86)"
	@echo "  push              Push les images vers le registry du bastion"
	@echo "  clean             Supprime les images buildées localement"
	@echo "  test              Lint tous les Dockerfiles avec hadolint"
	@echo "  shell             Ouvre un shell dans le container de build"
	@echo "  docker-build      Build le container de build"
	@echo ""
	@echo "  buildx-setup      Crée le builder buildx ARM64 (une seule fois)"
	@echo "  build-arm64       Build et push $(ARM64_SVC) pour linux/arm64 (VPN requis)"
	@echo "                    ARM64_SVC=$(ARM64_SVC)  IMAGE_TAG=$(IMAGE_TAG)"
	@echo ""
	@echo "  deploy-test       Applique le Job de test ARM64 sur le cluster K3s (VPN requis)"
	@echo "  logs-test         Affiche les logs du Job de test"
	@echo "  clean-test        Supprime le Job de test du cluster"
	@echo "                    KUBECONFIG=$(KUBECONFIG)"
	@echo ""
	@echo "  Prérequis build-arm64 :"
	@echo "    - QEMU : docker run --rm --privileged multiarch/qemu-user-static --reset -p yes"
	@echo "    - Registry insecure dans /etc/docker/daemon.json :"
	@echo "      { \"insecure-registries\": [\"$(REGISTRY)\"] }"
	@echo ""

docker-build:
	docker compose -f $(MODULE)/docker/compose.yaml build

test:
	docker compose -f $(MODULE)/docker/compose.yaml run --rm containers-test

shell:
	docker compose -f $(MODULE)/docker/compose.yaml run --rm containers-build bash

build:
	@for svc in $(SERVICES); do \
		echo "[build] $$svc → $(REGISTRY)/r2bewi/$$svc:$(IMAGE_TAG)"; \
		docker build \
			-t $(REGISTRY)/r2bewi/$$svc:$(IMAGE_TAG) \
			$(MODULE)/src/$$svc; \
	done

push:
	@for svc in $(SERVICES); do \
		echo "[push] $(REGISTRY)/r2bewi/$$svc:$(IMAGE_TAG)"; \
		docker push $(REGISTRY)/r2bewi/$$svc:$(IMAGE_TAG); \
	done

clean:
	@for svc in $(SERVICES); do \
		docker rmi $(REGISTRY)/r2bewi/$$svc:$(IMAGE_TAG) 2>/dev/null || true; \
	done

# ── ARM64 ─────────────────────────────────────────────────────────────────────

buildx-setup:
	@docker buildx inspect $(BUILDX_BUILDER) >/dev/null 2>&1 || { \
		docker buildx create \
			--name $(BUILDX_BUILDER) \
			--driver docker-container \
			--driver-opt network=host \
			--config $(MODULE)/docker/buildkitd.toml \
			--use && \
		docker buildx inspect --bootstrap $(BUILDX_BUILDER); \
	}
	@echo "[buildx] builder $(BUILDX_BUILDER) prêt"

build-arm64: buildx-setup
	@# Résoudre registry.r2bewi.internal sur l'hôte (VPN) et l'injecter dans buildkitd
	@REGISTRY_IP=$$(getent hosts $(REGISTRY_HOST) 2>/dev/null | awk '{print $$1}'); \
	if [ -z "$$REGISTRY_IP" ]; then \
		echo "[build-arm64] ERREUR : $(REGISTRY_HOST) non résolu — VPN actif ?"; exit 1; \
	fi; \
	CONTAINER=$$(docker ps --filter name=$(BUILDX_BUILDER) --format '{{.Names}}' | head -1); \
	if [ -z "$$CONTAINER" ]; then \
		echo "[build-arm64] ERREUR : container buildkitd $(BUILDX_BUILDER) introuvable"; exit 1; \
	fi; \
	docker exec $$CONTAINER sh -c \
		"grep -v '$(REGISTRY_HOST)' /etc/hosts > /tmp/hosts.new \
		 && cat /tmp/hosts.new > /etc/hosts \
		 && echo '$$REGISTRY_IP $(REGISTRY_HOST)' >> /etc/hosts"; \
	echo "[build-arm64] buildkitd : $(REGISTRY_HOST) → $$REGISTRY_IP"
	@echo "[build-arm64] $(ARM64_SVC) → $(REGISTRY)/r2bewi/$(ARM64_SVC):$(IMAGE_TAG)"
	docker buildx build \
		--builder $(BUILDX_BUILDER) \
		--platform $(PLATFORM) \
		--provenance=false \
		--output type=image,name=$(REGISTRY)/r2bewi/$(ARM64_SVC):$(IMAGE_TAG),push=true,compression=gzip,oci-mediatypes=false \
		$(MODULE)/src/$(ARM64_SVC)

# ── Test K3s ──────────────────────────────────────────────────────────────────

deploy-test:
	$(KUBECTL) delete job ros-core-arm64-test -n ros --ignore-not-found
	$(KUBECTL) apply -f - < $(MODULE)/manifests/ros-core-arm64-test.yaml
	@echo ""
	@echo "En attente du résultat..."
	$(KUBECTL) wait --for=condition=complete job/ros-core-arm64-test -n ros --timeout=120s
	@$(MAKE) logs-test

logs-test:
	$(KUBECTL) logs -n ros job/ros-core-arm64-test

clean-test:
	$(KUBECTL) delete job ros-core-arm64-test -n ros --ignore-not-found
