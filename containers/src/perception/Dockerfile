# Base NVIDIA L4T pour nœud ARM + GPU (JetPack 5 — Ubuntu 20.04)
FROM nvcr.io/nvidia/l4t-pytorch:r35.2.1-pth2.0-py3

RUN apt-get update && apt-get install -y --no-install-recommends \
    libopencv-dev \
    python3-pip \
    python3-opencv \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir \
    numpy \
    onnxruntime-gpu

CMD ["python3"]
