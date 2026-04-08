REGISTRY_HOST  ?= registry.r2bewi.internal
REGISTRY_PORT  ?= 5000
IMAGE_TAG      ?= latest
BASTION_HOST   ?= bastion.r2bewi.internal
SSH_USER       ?= iobewi
BOOTSTRAP_USER ?= ubuntu

.PHONY: help ssh-setup \
        bootstrap-build bootstrap-test bootstrap-lint \
        containers-build containers-push containers-clean containers-test

help:
	@echo ""
	@echo "R2BEWI SDK MANAGER"
	@echo ""
	@echo "  Bootstrap (CLI r2bewi)"
	@echo "    bootstrap-build       Construit le paquet .deb et le binaire .pyz"
	@echo "    bootstrap-test        Lance la suite pytest"
	@echo "    bootstrap-lint        Vérifie la syntaxe Python"
	@echo ""
	@echo "  Containers (Docker)"
	@echo "    containers-build      Construit les images Docker des services"
	@echo "    containers-push       Publie les images sur le registry du bastion"
	@echo "    containers-clean      Supprime les images locales"
	@echo "    containers-test       Lint des Dockerfiles (hadolint)"
	@echo ""
	@echo "  Accès SSH"
	@echo "    ssh-setup             Installe la clé SSH locale sur le bastion (une seule fois)"
	@echo "                          BOOTSTRAP_USER=$(BOOTSTRAP_USER)  SSH_USER=$(SSH_USER)"
	@echo "                          BASTION_HOST=$(BASTION_HOST)"
	@echo ""
	@echo "  Variables"
	@echo "    REGISTRY_HOST         Hôte du registry   (défaut : registry.r2bewi.internal)"
	@echo "    REGISTRY_PORT         Port du registry   (défaut : 5000)"
	@echo "    IMAGE_TAG             Tag de publication (défaut : latest)"
	@echo "    BASTION_HOST          Nom DNS du bastion (défaut : bastion.r2bewi.internal)"
	@echo "    BOOTSTRAP_USER        User intermédiaire (défaut : ubuntu)"
	@echo "    SSH_USER              User cible bastion (défaut : iobewi)"
	@echo ""

bootstrap-build:
	$(MAKE) -C bootstrap build

bootstrap-test:
	$(MAKE) -C bootstrap test-dev

bootstrap-lint:
	$(MAKE) -C bootstrap lint

containers-build:
	$(MAKE) -C containers build REGISTRY_HOST=$(REGISTRY_HOST) REGISTRY_PORT=$(REGISTRY_PORT) IMAGE_TAG=$(IMAGE_TAG)

containers-push:
	$(MAKE) -C containers push REGISTRY_HOST=$(REGISTRY_HOST) REGISTRY_PORT=$(REGISTRY_PORT) IMAGE_TAG=$(IMAGE_TAG)

containers-clean:
	$(MAKE) -C containers clean REGISTRY_HOST=$(REGISTRY_HOST) REGISTRY_PORT=$(REGISTRY_PORT) IMAGE_TAG=$(IMAGE_TAG)

containers-test:
	$(MAKE) -C containers test

# ── SSH ───────────────────────────────────────────────────────────────────────

ssh-setup:
	@test -f ~/.ssh/id_ed25519.pub || ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
	@B64=$$(base64 -w0 < ~/.ssh/id_ed25519.pub) && \
	ssh -t $(BOOTSTRAP_USER)@$(BASTION_HOST) \
		"sudo mkdir -p /home/$(SSH_USER)/.ssh && \
		 sudo chmod 700 /home/$(SSH_USER)/.ssh && \
		 sudo touch /home/$(SSH_USER)/.ssh/authorized_keys && \
		 sudo chmod 600 /home/$(SSH_USER)/.ssh/authorized_keys && \
		 sudo chown -R $(SSH_USER):$(SSH_USER) /home/$(SSH_USER)/.ssh && \
		 echo $$B64 | base64 -d | sudo tee -a /home/$(SSH_USER)/.ssh/authorized_keys > /dev/null"
	@echo "Clé installée — test : ssh $(SSH_USER)@$(BASTION_HOST) echo ok"
