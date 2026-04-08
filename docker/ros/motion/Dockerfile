ARG REGISTRY=registry.r2bewi.internal:5000
FROM ${REGISTRY}/r2bewi/core:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-jazzy-control-msgs \
    ros-jazzy-controller-manager \
    ros-jazzy-ros2-control \
    ros-jazzy-ros2-controllers \
    && rm -rf /var/lib/apt/lists/*
