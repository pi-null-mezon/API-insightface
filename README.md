# API_insightface
HTTP service for face verification and recognition based on insightface deep models and [iFace](https://documenter.getpostman.com/view/1169404/TVK8ZJzz) API-calls convention

*Build for CPU inference*

```
sudo docker build --force-rm -t iface:cpu . 
```

*Run*

```
sudo docker run -d --rm -v "${PWD}":/usr/src/app -p 5000:5000 iface:cpu
```

*Build for GPU inference*


Check installed Nvidia driver and select appropriate nvidia/cuda image in Dockerfile_CUDA FROM section. Then run:

```
sudo docker build --force-rm -t iface:gpu -f Dockerfile_CUDA . 
```

*Run*

```
sudo docker run --gpus all -d --rm -v "${PWD}":/usr/src/app -p 5000:5000 iface:gpu
```

GPU inference in average 10-times faster than CPU (tested on GTX 1070 vs Core-i5 6600) and templates are interchangable
