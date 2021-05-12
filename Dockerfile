FROM python:3.8-slim

WORKDIR /usr/src/app

RUN apt-get update && \
apt-get install git wget unzip libglib2.0-0 libgl1-mesa-dev -y && \
git clone https://github.com/deepinsight/insightface.git && \
pip install --upgrade pip && \
pip install --no-cache-dir onnx onnxruntime flask waitress pypandoc scikit-image && \
cd insightface/python-package && python setup.py install && \
wget https://github.com/pi-null-mezon/deepmodels/raw/main/antelope.zip && \
mkdir -p ~/.insightface/models && \
unzip -d ~/.insightface/models antelope.zip && \
rm antelope.zip

EXPOSE 5000

ENTRYPOINT ["python", "./httpsrv.py"]