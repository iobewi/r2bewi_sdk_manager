FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Europe/Paris
ENV IN_DOCKER=1

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    git \
    jq \
 && install -d -m 0755 /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    -o /etc/apt/keyrings/docker.asc \
 && chmod a+r /etc/apt/keyrings/docker.asc \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
    https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo ${UBUNTU_CODENAME}) stable" \
    > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y docker-ce-cli docker-buildx-plugin \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL "https://github.com/hadolint/hadolint/releases/download/v2.12.0/hadolint-Linux-x86_64" \
    -o /usr/local/bin/hadolint \
 && chmod +x /usr/local/bin/hadolint

WORKDIR /workspace
CMD ["/bin/bash"]
