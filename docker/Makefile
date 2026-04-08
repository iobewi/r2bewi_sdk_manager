REGISTRY_HOST  ?= registry.r2bewi.internal
REGISTRY_PORT  ?= 5000
IMAGE_TAG      ?= latest
MODULE          := $(shell pwd)

REGISTRY       = $(REGISTRY_HOST):$(REGISTRY_PORT)
SERVICES       = zenoh-router core motion perception

PLATFORM       ?= linux/arm64
ARM64_SVC      ?= core
BUILDX_BUILDER ?= r2bewi-arm64

.PHONY: help shell build-env push clean test buildx-setup build-arm64

help:
	@echo ""
	@echo "R2BEWI SDK MANAGER — Images Docker"
	@echo ""
	@echo "  build-env         Build le container d'environnement SDK"
	@echo "  shell             Ouvre un shell dans le container SDK"
	@echo "  build             Build toutes les images ROS (x86)"
	@echo "  push              Push les images vers le registry du bastion"
	@echo "  clean             Supprime les images buildées localement"
	@echo "  test              Lint tous les Dockerfiles avec hadolint"
	@echo ""
	@echo "  buildx-setup      Crée le builder buildx ARM64 (une seule fois)"
	@echo "  build-arm64       Build et push $(ARM64_SVC) pour linux/arm64 (VPN requis)"
	@echo "                    ARM64_SVC=$(ARM64_SVC)  IMAGE_TAG=$(IMAGE_TAG)"
	@echo ""
	@echo "  Prérequis build-arm64 :"
	@echo "    - QEMU : docker run --rm --privileged multiarch/qemu-user-static --reset -p yes"
	@echo "    - Registry insecure dans /etc/docker/daemon.json :"
	@echo "      { \"insecure-registries\": [\"$(REGISTRY)\"] }"
	@echo ""

build-env:
	docker compose -f $(MODULE)/core/sdk/compose.yaml build

shell:
	docker compose -f $(MODULE)/core/sdk/compose.yaml run --rm r2bewi-sdk-manager bash

build:
	@for svc in $(SERVICES); do \
		echo "[build] $$svc → $(REGISTRY)/r2bewi/$$svc:$(IMAGE_TAG)"; \
		docker build \
			--build-arg REGISTRY=$(REGISTRY) \
			-t $(REGISTRY)/r2bewi/$$svc:$(IMAGE_TAG) \
			$(MODULE)/ros/$$svc; \
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

test:
	bash $(MODULE)/lint.sh

# ── ARM64 ─────────────────────────────────────────────────────────────────────

buildx-setup:
	@docker buildx inspect $(BUILDX_BUILDER) >/dev/null 2>&1 || { \
		docker buildx create \
			--name $(BUILDX_BUILDER) \
			--driver docker-container \
			--driver-opt network=host \
			--config $(MODULE)/core/buildkit/buildkitd.toml \
			--use && \
		docker buildx inspect --bootstrap $(BUILDX_BUILDER); \
	}
	@echo "[buildx] builder $(BUILDX_BUILDER) prêt"

build-arm64: buildx-setup
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
		--build-arg REGISTRY=$(REGISTRY) \
		--output type=image,name=$(REGISTRY)/r2bewi/$(ARM64_SVC):$(IMAGE_TAG),push=true,compression=gzip,oci-mediatypes=false \
		$(MODULE)/ros/$(ARM64_SVC)
