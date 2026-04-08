FROM ros:jazzy

RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-jazzy-ros-base \
    ros-jazzy-control-msgs \
    ros-jazzy-controller-manager \
    ros-jazzy-ros2-control \
    ros-jazzy-ros2-controllers \
    && rm -rf /var/lib/apt/lists/*

SHELL ["/bin/bash", "-c"]
RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc

CMD ["ros2", "launch"]
