ARG REGISTRY=registry.r2bewi.internal:5000
FROM ${REGISTRY}/r2bewi/core:latest

# Le router Zenoh est fourni par ros-jazzy-rmw-zenoh-cpp (déjà installé dans core).
# Sans ce router, les nœuds ne peuvent pas se découvrir — la découverte multicast
# est désactivée par défaut dans rmw_zenoh_cpp.

EXPOSE 7447/tcp
EXPOSE 7447/udp

SHELL ["/bin/bash", "-c"]
CMD ["source /opt/ros/jazzy/setup.bash && ros2 run rmw_zenoh_cpp rmw_zenohd"]
