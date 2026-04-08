FROM eclipse/zenoh:latest

# Configuration par défaut — peut être surchargée via volume :
#   docker run -v ./zenoh.json5:/zenoh.json5 r2bewi/zenoh-router
#
# Points d'écoute :
#   TCP  0.0.0.0:7447  — agents ROS2 (rmw_zenoh_cpp)
#   HTTP 0.0.0.0:8000  — API REST (monitoring optionnel)

EXPOSE 7447/tcp
EXPOSE 7447/udp
EXPOSE 8000/tcp

CMD ["zenohd"]
