# API_insightface
HTTP service for face verification and recognition based on insightface deep models and OpenIRT calls convention

*Build for CPU inference*

```
sudo docker build --force-rm -t iface . 
```

*Run*

```
sudo docker run -d --rm -v "${PWD}":/usr/src/app -p 5000:5000 iface
```
