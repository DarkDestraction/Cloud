"""
Esempio di `app.py` semplificato per sviluppo. NON contiene segreti né configurazioni
sensibili; usare variabili d'ambiente e un database reale in produzione.

Questo file è pensato come riferimento/starting-point per deploy sicuro.
"""
import os
import json
import hashlib
import shutil
import zipfile
from io import BytesIO
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory, send_file, session
from werkzeug.utils import secure_filename

# ---------- Config (usare env vars in produzione) ----------
app = Flask(__name__)
app.secret_key = os.environ.get('MYCLOUD_SECRET', 'change-me-in-production')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')

FILES_FOLDER = os.path.join(STATIC_DIR, 'files')
GALLERY_FOLDER = os.path.join(STATIC_DIR, 'gallery')

os.makedirs(FILES_FOLDER, exist_ok=True)
os.makedirs(GALLERY_FOLDER, exist_ok=True)

# Extensions support
IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
VIDEO_EXT = ('.mp4', '.webm', '.mov')
MEDIA_EXT = IMAGE_EXT + VIDEO_EXT

# Quota (esempio)
MAX_USER_SPACE = 20 * 1024 * 1024 * 1024  # 20 GB

# Users file (dev only) - NON committare la versione reale
USERS_FILE = 'users.json'

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def get_user_base():
    user = session.get('user')
    if not user:
        return None, None
    files_base = os.path.join(FILES_FOLDER, user)
    gallery_base = os.path.join(GALLERY_FOLDER, user)
    os.makedirs(files_base, exist_ok=True)
    os.makedirs(gallery_base, exist_ok=True)
    return files_base, gallery_base

def get_folder_size(path):
    total = 0
    if not os.path.exists(path):
        return 0
    for root, _, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total

def check_quota(extra_bytes=0):
    user = session.get('user')
    if not user:
        return False, 'Not authenticated'
    users = load_users()
    role = users.get(user, {}).get('role', 'user')
    if role == 'admin':
        return True, None
    files_base, gallery_base = get_user_base()
    used = get_folder_size(files_base) + get_folder_size(gallery_base)
    if used + extra_bytes > MAX_USER_SPACE:
        return False, 'Quota exceeded'
    return True, None

def build_file_tree(root):
    tree = {"_files": []}
    if not os.path.exists(root):
        return tree
    for item in os.listdir(root):
        path = os.path.join(root, item)
        if os.path.isdir(path):
            tree[item] = build_file_tree(path)
        else:
            try:
                stat = os.stat(path)
                tree["_files"].append({
                    "name": item,
                    "size": stat.st_size,
                    "lastModified": int(stat.st_mtime)
                })
            except OSError:
                pass
    return tree

@app.route('/')
def home():
    return send_from_directory('static', 'index.html')

@app.route('/api/files')
def get_files():
    files_base, _ = get_user_base()
    if not files_base:
        return jsonify({'error': 'unauthenticated'}), 401
    return jsonify(build_file_tree(files_base))

@app.route('/api/files/upload', methods=['POST'])
def upload_file():
    user = session.get('user')
    if not user:
        return jsonify({'error': 'unauthenticated'}), 401
    rel_path = request.args.get('path', '').strip()
    files = request.files.getlist('file')
    # quota check
    total = 0
    for f in files:
        data = f.read()
        total += len(data)
    for f in files:
        f.seek(0)
    ok, err = check_quota(total)
    if not ok:
        return jsonify({'error': err}), 400
    target = os.path.join(FILES_FOLDER, user, rel_path)
    os.makedirs(target, exist_ok=True)
    for f in files:
        filename = secure_filename(f.filename)
        f.save(os.path.join(target, filename))
    return jsonify(success=True)

@app.route('/api/files/download')
def download_file():
    files_base, _ = get_user_base()
    if not files_base:
        return jsonify({'error': 'unauthenticated'}), 401
    rel_path = request.args.get('path', '')
    full_path = os.path.join(files_base, rel_path)
    if not os.path.abspath(full_path).startswith(os.path.abspath(files_base)):
        return jsonify({'error': 'invalid path'}), 400
    if not os.path.exists(full_path):
        return jsonify({'error': 'not found'}), 404
    return send_file(full_path, as_attachment=True)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username')
    # NOTE: example: this does NOT validate password. Replace with real auth.
    if not username:
        return jsonify({'error': 'missing username'}), 400
    session['user'] = username
    return jsonify({'success': True})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    return jsonify({'success': True})

@app.route('/api/quota')
def quota():
    user = session.get('user')
    if not user:
        return jsonify({'error': 'unauthenticated'}), 401
    files_base, gallery_base = get_user_base()
    used = get_folder_size(files_base) + get_folder_size(gallery_base)
    return jsonify(role='user', used=used, max=MAX_USER_SPACE)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000)
