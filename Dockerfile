FROM python:3.6-slim

COPY httpsrv.py /usr/src/app/
COPY antelope.zip /usr/src/app/

WORKDIR /usr/src/app

RUN apt-get update && \
apt-get install git wget unzip libglib2.0-0 libgl1-mesa-dev pandoc -y && \
git clone --single-branch --branch printless https://github.com/pi-null-mezon/insightface.git && \
pip install --upgrade pip && \
pip install --no-cache-dir onnx==1.6.0 onnxruntime==1.6.0 flask waitress pypandoc==1.4 scikit-learn==0.24 scikit-image==0.17.2 && \
cd ./insightface && cd ./python-package && python setup.py install && \
cd /usr/src/app && \
#wget https://github.com/pi-null-mezon/deepmodels/raw/main/antelope.zip && \
mkdir -p ~/.insightface/models && \
unzip -d ~/.insightface/models antelope.zip && \
rm antelope.zip

EXPOSE 5000

ENTRYPOINT ["python", "./httpsrv.py"]
