REGISTRY_HOST  ?= registry.r2bewi.internal
IMAGE_TAG      ?= latest
MODULE          := $(shell pwd)

KUBECONFIG     ?= $(HOME)/.kube/r2bewi.yaml
KUBECTL        ?= kubectl --kubeconfig=$(KUBECONFIG)

.PHONY: help deploy-test logs-test clean-test

help:
	@echo ""
	@echo "R2BEWI SDK MANAGER — Manifests K3s"
	@echo ""
	@echo "  deploy-test       Applique le Job de test ARM64 sur le cluster K3s (VPN requis)"
	@echo "  logs-test         Affiche les logs du Job de test"
	@echo "  clean-test        Supprime le Job de test du cluster"
	@echo "                    KUBECONFIG=$(KUBECONFIG)"
	@echo ""

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
