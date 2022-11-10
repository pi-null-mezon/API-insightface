# -----------------------------------------------------------------
# Face recognition http server
#
# (C) 2020 Alex A. Taranov, Moscow, Russia
# email a.a.taranov@nefrosovet.ru
# -----------------------------------------------------------------
import base64
import json
import os
import requests
import subprocess
import sys
import uuid
import flask
import socket
import struct
from waitress import serve
from werkzeug.utils import secure_filename
from insightface.app import FaceAnalysis
import cv2
import numpy as np
import argparse
import pickle

OS_WIN = False
if sys.platform == 'win32':
    OS_WIN = True
    
# Specify API routing prefix
api_prefix = os.getenv('API_PREFIX', '/iface')

# Specify where files should be stored on upload
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', '/var/iface/local_storage')
if OS_WIN:
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'C:/Testdata/iface/local_storage')
if not os.path.isdir(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
# Specify allowed files extensions
ALLOWED_EXTENSIONS = set(['jpg', 'jpeg', 'png'])

# Flask's stuff
app = flask.Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# Identities
parser = argparse.ArgumentParser(description='insightface http server')
parser.add_argument('--ctx', default=0, type=int, help='ctx id, <0 means using cpu')
parser.add_argument('--labels', default='./labels.pkl', help='where labels are stored')
parser.add_argument('--thresh', default=0.33, type=float, help='where labels are stored')
args = parser.parse_args()

identities = dict()
if os.path.isfile(args.labels):
    with open(args.labels, 'rb') as labels_file:
        identities = pickle.load(labels_file)


def sim_score(et, vt):
    return (1.0 + float(np.dot(et, vt.T))) / 2.0


def next_free_label():
    max_label = -1
    for item in identities:
        if identities[item]['label'] > max_label:
            max_label = identities[item]['label']
    return max_label + 1


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def randomize_name(filename):
    return str(uuid.uuid4()) + '.' + filename.rsplit('.', 1)[1].lower()


@app.route("%s/status" % api_prefix, methods=['GET'])
def get_status():
    return flask.jsonify({'status': 'Success', 'version': '2.0.0.1'}), 200


@app.route("%s/photo" % api_prefix, methods=['GET'])
def get_photo_v1():
    labelinfo = base64.urlsafe_b64encode(flask.request.form['labelinfo'].encode('utf-8')).decode('utf-8')
    labelslist = [f.name.rsplit('.', 1)[0] for f in os.scandir(app.config['UPLOAD_FOLDER']) if f.is_file()]
    if labelinfo in labelslist:
        for extension in ALLOWED_EXTENSIONS:
            filename = os.path.join(app.config['UPLOAD_FOLDER'], f"{labelinfo}.{extension}")
            if os.path.isfile(filename):
                return flask.send_from_directory(app.config['UPLOAD_FOLDER'], f"{labelinfo}.{extension}",
                                                 as_attachment=True)
    return flask.jsonify({"status": "Error", "info": "No such labelinfo found or incorrect targetnum asked"}), 400


@app.route("%s/photo/<labelinfo>" % api_prefix, methods=['GET'])
def get_photo_v2(labelinfo):
    labelinfo = base64.urlsafe_b64encode(labelinfo.encode('utf-8')).decode('utf-8')
    labelslist = [f.name.rsplit('.', 1)[0] for f in os.scandir(app.config['UPLOAD_FOLDER']) if f.is_file()]
    if labelinfo in labelslist:
        for extension in ALLOWED_EXTENSIONS:
            filename = os.path.join(app.config['UPLOAD_FOLDER'], f"{labelinfo}.{extension}")
            if os.path.isfile(filename):
                return flask.send_from_directory(app.config['UPLOAD_FOLDER'], f"{labelinfo}.{extension}",
                                                 as_attachment=True)
    return flask.jsonify({"status": "Error", "info": "No such labelinfo found"}), 400


@app.route("%s/remember" % api_prefix, methods=['POST'])
def remember_face():
    if 'file' not in flask.request.files:
        return flask.jsonify({"status": "Error", "info": "file part is missing in request"}), 400
    file = flask.request.files['file']
    if file.filename == '':
        return flask.jsonify({"status": "Error", "info": "Empty file name parameter"}), 400
    labelinfo = flask.request.form['labelinfo']
    if file and allowed_file(file.filename):
        filepath = os.path.join(app.config['UPLOAD_FOLDER'],
                                str(base64.urlsafe_b64encode(labelinfo.encode('utf-8')).decode('utf-8')) + '.' +
                                file.filename.rsplit('.', 1)[1])
        file.save(filepath)
        img = cv2.imread(filepath, cv2.IMREAD_UNCHANGED)
        faces = fa.get(img)
        if len(faces) == 0:
            os.remove(filepath)
            return flask.jsonify({"status": "Error", "code": 2, "message": "No faces"}), 400
        elif len(faces) > 1:
            os.remove(filepath)
            return flask.jsonify({"status": "Error", "code": 3, "message": "Many faces"}), 400
        if labelinfo not in identities:
            identities[labelinfo] = {'label': next_free_label(),
                                     'whitelist': True,
                                     'templates': [faces[0].normed_embedding]}
        else:
            identities[labelinfo]['templates'].append(faces[0].normed_embedding)
    with open(args.labels, 'wb') as labels_file:
        pickle.dump(identities, labels_file)
    return flask.jsonify({"status": "Success",
                          "label": identities[labelinfo]['label'],
                          "labelinfo": labelinfo,
                          "templates": len(identities[labelinfo]['templates']),
                          "whitelist": identities[labelinfo]['whitelist']}), 200


@app.route("%s/delete" % api_prefix, methods=['DELETE'])
def delete_template():
    if len(identities) == 0:
        flask.jsonify({"status": "Error", "message": "Empty labels list, can not delete anything!"}), 400
    labelinfo = flask.request.form['labelinfo']
    if labelinfo in identities:
        # Remove photo from disk
        encodedlabelinfo = base64.urlsafe_b64encode(labelinfo.encode('utf-8')).decode('utf-8')
        for extension in ALLOWED_EXTENSIONS:
            filename = os.path.join(app.config['UPLOAD_FOLDER'], f"{encodedlabelinfo}.{extension}")
            if os.path.isfile(filename):
                os.remove(filename)
        # Remove templates & etc.
        del identities[labelinfo]
        with open(args.labels, 'wb') as labels_file:
            pickle.dump(identities, labels_file)
        return flask.jsonify({"status": "Success", "message": f"{labelinfo} has been deleted"}), 200
    return flask.jsonify({"status": "Error", "message": f"No {labelinfo} has been found in labels list!"}), 400


@app.route("%s/identify" % api_prefix, methods=['POST'])
def identify_face():
    if len(identities) == 0:
        return flask.jsonify({"status": "Error", "message": "Empty labels list, can not identify anything!"}), 400
    if 'file' not in flask.request.files:
        return flask.jsonify({"status": "Error", "info": "file part is missing in request"}), 400
    file = flask.request.files['file']
    if file.filename == '':
        return flask.jsonify({"status": "Error", "info": "Empty filename parameter"}), 400
    if file and allowed_file(file.filename):
        img = cv2.imdecode(np.frombuffer(file.read(), np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return flask.jsonify({"status": "Error", "code": 4, "message": "Can not decode photo"}), 400    
        faces = fa.get(img)
        if len(faces) == 0:
            return flask.jsonify({"status": "Error", "code": 2, "message": "No faces"}), 400
        elif len(faces) > 1:
            return flask.jsonify({"status": "Error", "code": 3, "message": "Many faces"}), 400
        vt = faces[0].normed_embedding
        max_similarity = 0
        labelinfo = ""
        for item in identities:
            if identities[item]['whitelist']:
                for et in identities[item]['templates']:
                    similarity = sim_score(et, vt)
                    if similarity > max_similarity:
                        max_similarity = similarity
                        labelinfo = item
        return flask.jsonify({"status": "Success",
                              "labelinfo": labelinfo,
                              "label": identities[labelinfo]["label"],
                              "distance": 1.0 - max_similarity,
                              "distancethresh": args.thresh}), 200
    return flask.jsonify({"status": "Error", "info": "File you have try to upload seems to be bad"}), 400


@app.route("%s/recognize" % api_prefix, methods=['POST'])
def recognize_face():
    if 'file' not in flask.request.files:
        return flask.jsonify({"status": "Error", "info": "file part is missing in request"}), 400
    file = flask.request.files['file']
    if file.filename == '':
        return flask.jsonify({"status": "Error", "info": "Empty filename parameter"}), 400
    if file and allowed_file(file.filename):
        img = cv2.imdecode(np.frombuffer(file.read(), np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return flask.jsonify({"status": "Error", "code": 4, "message": "Can not decode photo"}), 400
        faces = fa.get(img)
        if len(faces) == 0:
            return flask.jsonify({"status": "Error", "code": 2, "message": "No faces"}), 400
        elif len(faces) > 1:
            return flask.jsonify({"status": "Error", "code": 3, "message": "Many faces"}), 400
        vt = faces[0].normed_embedding
        predictions = []
        thresh = 1.0 - args.thresh
        for item in identities:
            if identities[item]['whitelist']:
                for et in identities[item]['templates']:
                    similarity = sim_score(et, vt)
                    if similarity > thresh:
                        predictions.append({"labelinfo": item,
                                            "label": identities[item]["label"],
                                            "distance": 1.0 - similarity,
                                            "distancethresh": args.thresh})
        if len(predictions) == 0:
            return flask.jsonify({"status": "Error",
                                  "message": "Can not find anything close enough to this image!"}), 400
        else:
            sorted_predictions = sorted(predictions, key=lambda x: x['distance'])
            return flask.jsonify({"status": "Success", "predictions": sorted_predictions}), 200
    return flask.jsonify({"status": "Error", "info": "File you have try to upload seems to be bad"}), 400


@app.route("%s/labels" % api_prefix, methods=['GET'])
def get_labels():
    json_array = []
    for item in identities:
        json_array.append({"label": identities[item]["label"],
                           "labelinfo": item,
                           "templates": len(identities[item]["templates"]),
                           "whitelist": identities[item]["whitelist"]})
    return flask.jsonify({"status": "Success", "labels": json_array}), 200


@app.route("%s/verify" % api_prefix, methods=['POST'])
def verify_face():
    if 'efile' not in flask.request.files:
        return flask.jsonify({"status": "Error", "info": "efile part is missing in request"}), 400
    efile = flask.request.files['efile']
    if efile.filename == '':
        return flask.jsonify({"status": "Error", "info": "Empty efile name parameter"}), 400
    if 'vfile' not in flask.request.files:
        return flask.jsonify({"status": "Error", "info": "vfile part is missing in request"}), 400
    vfile = flask.request.files['vfile']
    if vfile.filename == '':
        return flask.jsonify({"status": "Error", "info": "Empty vfile name parameter"}), 400
    if efile and allowed_file(efile.filename) and vfile and allowed_file(vfile.filename):
        img = cv2.imdecode(np.frombuffer(efile.read(), np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return flask.jsonify({"status": "Error", "code": 4, "message": "Can not decode photo"}), 400
        efaces = fa.get(img)
        if len(efaces) == 0:
            return flask.jsonify({"status": "Error", "code": 2, "message": "No faces"}), 400
        elif len(efaces) > 1:
            return flask.jsonify({"status": "Error", "code": 3, "message": "Many faces"}), 400
        et = efaces[0].normed_embedding

        img = cv2.imdecode(np.frombuffer(vfile.read(), np.uint8), cv2.IMREAD_COLOR)
        vfaces = fa.get(img)
        if len(vfaces) == 0:
            return flask.jsonify({"status": "Error", "code": 2, "message": "No faces"}), 400
        elif len(vfaces) > 1:
            return flask.jsonify({"status": "Error", "code": 3, "message": "Many faces"}), 400
        vt = vfaces[0].normed_embedding
        return flask.jsonify({"status": "Success",
                              "distance": 1.0 - sim_score(et, vt),
                              "distancethresh": args.thresh}), 200
    return flask.jsonify({"status": "Error", "info": "Files you have try to upload seems to be bad"}), 400


@app.route("%s/whitelist" % api_prefix, methods=['POST'])
def set_whitelist():
    if not flask.request.is_json:
        return flask.jsonify({"status": "Error", "info": "Your input is not JSON"}), 400
    whitelist = flask.request.get_json()
    for item in identities:
        if item in whitelist:
            identities[item]['whitelist'] = True
        else:
            identities[item]['whitelist'] = False
    return flask.jsonify({"status": "Success", "message": "Whitelist has been updated"}), 200


@app.route("%s/whitelist/drop" % api_prefix, methods=['POST'])
def drop_whitelist():
    for item in identities:
        identities[item]['whitelist'] = True
    return flask.jsonify({"status": "Success", "message": "Whitelist has been updated"}), 200


if __name__ == "__main__":
    fa = FaceAnalysis(name='antelope', root='~/.insightface/models')
    fa.prepare(ctx_id=args.ctx)
    app_addr = os.getenv('APP_ADDR', '0.0.0.0')
    ap_port = int(os.getenv('APP_PORT', 5000))
    print("---------------------------------------")
    print(f" - upload folder:   {app.config['UPLOAD_FOLDER']}")
    print(f" - labels file:     {args.labels}")
    print(f" - distance thresh: {args.thresh}")
    print("---------------------------------------")
    print(f"Start listening on {app_addr}:{ap_port}{api_prefix}", flush=True)
    serve(app, host=app_addr, port=ap_port)
