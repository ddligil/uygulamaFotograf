# app.py
import os, json, uuid, io, base64
from datetime import datetime
from flask import Flask, request, render_template, redirect, url_for, session, send_from_directory, jsonify, flash
from werkzeug.utils import secure_filename
from PIL import Image

# OpenAI SDK (v1)
from openai import OpenAI

from face_engine import (
    EVENTS_DIR, USERS_DIR, ensure_event_dirs, add_event_photo,
    save_json, load_json, find_matches
)

app = Flask(__name__)
app.secret_key = "change-this-in-prod"
STORAGE_PATH = "storage.json"
ALLOWED = {"png","jpg","jpeg","webp"}

# --------- Yardımcılar ---------
def storage():
    obj = load_json(STORAGE_PATH, {"users": {}, "events": {}})
    return obj

def save_storage(obj):
    save_json(STORAGE_PATH, obj)

def allowed_file(name):
    return "." in name and name.rsplit(".",1)[1].lower() in ALLOWED

def _img_path_for_event_photo(event_id: str, photo_name: str) -> str:
    photos_dir, _ = ensure_event_dirs(event_id)
    return os.path.join(photos_dir, photo_name)

def _load_and_downsize_as_data_url(path: str, max_side: int = 640, quality: int = 85) -> str:
    """
    Görseli açar, en uzun kenarı max_side olacak şekilde küçültür, JPEG'e çevirip
    base64 data URL döndürür (OpenAI'ye göndermek için güvenli).
    """
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        scale = min(1.0, float(max_side) / float(max(w, h)))
        if scale < 1.0:
            im = im.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"

# --------- Sayfalar ---------
@app.route("/", methods=["GET"])
def home():
    return render_template(
        "index.html",
        user=session.get("user"),
        role=session.get("role"),
        events=storage().get("events",{})
    )

@app.route("/album", methods=["GET"])
def album_page():
    # Albüm sayfası client-side localStorage kullanıyor (album.html içinde)
    return render_template(
        "album.html",
        user=session.get("user"),
        role=session.get("role")
    )

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username","").strip()
    role = request.form.get("role","").strip()  # "photographer" | "guest"
    if not username or role not in ("photographer","guest"):
        flash("Kullanıcı adı ve rol gerekli.")
        return redirect(url_for("home"))
    s = storage()
    s["users"].setdefault(username, {"role": role})
    save_storage(s)
    session["user"] = username
    session["role"] = role
    return redirect(url_for("home"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

# ---- Fotoğrafçı akışı ----
@app.route("/event/create", methods=["POST"])
def create_event():
    if session.get("role") != "photographer":
        flash("Bu işlem için fotoğrafçı olarak giriş yapın.")
        return redirect(url_for("home"))
    name = request.form.get("event_name","").strip()
    if not name:
        flash("Event adı boş olamaz.")
        return redirect(url_for("home"))
    ev_id = uuid.uuid4().hex[:8].upper()
    s = storage()
    s["events"][ev_id] = {
        "name": name,
        "created_by": session["user"],
        "created_at": datetime.utcnow().isoformat(),
        "photos": []
    }
    save_storage(s)
    ensure_event_dirs(ev_id)
    flash(f"Event oluşturuldu. ID: {ev_id}")
    return redirect(url_for("event_page", event_id=ev_id))

@app.route("/event/<event_id>", methods=["GET"])
def event_page(event_id):
    s = storage()
    ev = s["events"].get(event_id)
    if not ev:
        flash("Event bulunamadı.")
        return redirect(url_for("home"))
    photos_dir, _ = ensure_event_dirs(event_id)
    try:
        current_photos = sorted(os.listdir(photos_dir))
    except Exception:
        current_photos = []
    return render_template(
        "index.html",
        user=session.get("user"),
        role=session.get("role"),
        view_event=ev,
        event_id=event_id,
        event_photos=current_photos,
        events=s.get("events", {})
    )

@app.route("/event/<event_id>/upload", methods=["POST"])
def event_upload(event_id):
    if session.get("role") != "photographer":
        flash("Yükleme için fotoğrafçı girişi gerekir.")
        return redirect(url_for("home"))
    s = storage()
    if event_id not in s["events"]:
        flash("Event bulunamadı.")
        return redirect(url_for("home"))

    files = request.files.getlist("photos")
    if not files:
        flash("Dosya seçilmedi.")
        return redirect(url_for("event_page", event_id=event_id))
    photos_dir, _ = ensure_event_dirs(event_id)
    added = 0
    for f in files:
        if f and allowed_file(f.filename):
            name = secure_filename(f.filename)
            save_path = os.path.join(photos_dir, name)
            f.save(save_path)
            add_event_photo(event_id, save_path)  # yüz kodlarını güncelle
            s["events"][event_id]["photos"].append(name)
            added += 1
    save_storage(s)
    flash(f"{added} fotoğraf eklendi ve kodlandı.")
    return redirect(url_for("event_page", event_id=event_id))

# ---- Misafir (kullanıcı) arama akışı ----
@app.route("/search", methods=["POST"])
def search():
    if session.get("role") not in ("guest","photographer"):
        flash("Önce giriş yapın.")
        return redirect(url_for("home"))
    event_id = request.form.get("event_id","").strip().upper()
    # Euclidean distance: DÜŞÜK daha katı → default 0.60
    threshold = float(request.form.get("threshold","0.60"))
    deep = request.form.get("deep") == "1"

    if not event_id:
        flash("Event ID gerekli.")
        return redirect(url_for("home"))
    s = storage()
    if event_id not in s["events"]:
        flash("Event bulunamadı.")
        return redirect(url_for("home"))

    files = request.files.getlist("face")
    valid_files = [f for f in files if f and allowed_file(f.filename)]
    if not valid_files:
        flash("Geçerli bir yüz fotoğrafı yükleyin.")
        return redirect(url_for("home"))

    uname = session.get("user","guest")
    udir = os.path.join(USERS_DIR, uname)
    os.makedirs(udir, exist_ok=True)

    query_paths = []
    for f in valid_files:
        face_path = os.path.join(udir, "query_"+uuid.uuid4().hex[:6]+".jpg")
        f.save(face_path)
        query_paths.append(face_path)

    matches = find_matches(event_id, query_paths, threshold=threshold, deep=deep)
    return render_template(
        "index.html",
        user=session.get("user"),
        role=session.get("role"),
        search_results=matches,
        event_id=event_id,
        results_count=len(matches)
    )

# Event fotoğraflarını servis et
@app.route("/event/<event_id>/photos/<name>")
def serve_event_photo(event_id, name):
    photos_dir, _ = ensure_event_dirs(event_id)
    return send_from_directory(photos_dir, name)

# Basit sağlık kontrolü / JSON API örneği
@app.route("/api/events", methods=["GET"])
def api_events():
    return jsonify(storage().get("events", {}))

# --------- AI Albüm Sorgusu ---------
@app.route("/api/album_ai_query", methods=["POST"])
def api_album_ai_query():
    """
    Body (JSON):
    {
      "query": "güneş gözlüklü olduğum fotolar",
      "items": [{ "eventId": "AB12CD34", "photo": "IMG_001.jpg" }, ...],
      "top_k": 24    # opsiyonel
    }
    Döner:
    {
      "matches": [
        {"eventId": "...", "photo": "...", "score": 0.91, "reason": "sunglasses detected", "tags": ["sunglasses","outdoor"]},
        ...
      ]
    }
    """
    if not os.getenv("OPENAI_API_KEY"):
        return jsonify({"error": "Server OPENAI_API_KEY is not set."}), 500

    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    items = data.get("items") or []
    top_k = int(data.get("top_k") or 24)

    if not query or not items:
        return jsonify({"error": "query ve items zorunlu."}), 400

    # Albümden gelen öğeleri güvenli sayıda kısıtla
    items = items[:max(1, min(top_k, 48))]  # güvenli üst sınır

    # Her görseli küçültüp data URL hazırla
    payload_images = []
    print(f"DEBUG: Processing {len(items)} items for AI query: {query}")
    for it in items:
        event_id = it.get("eventId")
        photo = it.get("photo")
        if not event_id or not photo:
            print(f"DEBUG: Skipping item - missing eventId or photo: {it}")
            continue
        img_path = _img_path_for_event_photo(event_id, photo)
        print(f"DEBUG: Looking for image at: {img_path}")
        if not os.path.exists(img_path):
            print(f"DEBUG: Image not found: {img_path}")
            continue
        try:
            data_url = _load_and_downsize_as_data_url(img_path, max_side=640, quality=85)
            print(f"DEBUG: Successfully loaded image: {event_id}::{photo}")
        except Exception as e:
            print(f"DEBUG: Failed to load image {event_id}::{photo}: {e}")
            continue
        payload_images.append({
            "id": f"{event_id}::{photo}",
            "eventId": event_id,
            "photo": photo,
            "data_url": data_url
        })

    if not payload_images:
        return jsonify({"error": f"Hiçbir görsel yüklenemedi. Toplam {len(items)} item, {len(payload_images)} yüklendi."}), 400

    # OpenAI Vision çağrısı
    client = OpenAI()
    system_prompt = (
        "You are a visual search assistant. "
        "Look at the images and find matches for the user query. "
        "Return JSON with 'matches' array. Each match should have: "
        "id, score (0-1), reason (short description), tags (array). "
        "Be generous with matches - if there's any visual similarity, include it."
    )

    # Mesaj içeriği: önce metinsel talep, sonra görseller
    # OpenAI multimodal content: text + images via data URLs
    user_content = [
        {"type": "text", "text": f"Kullanıcı sorgusu (TR): {query}\n"
                                 f"Lütfen sadece JSON döndür: {{\"matches\": [{{\"id\": \"eventId::photo\", \"score\": 0.0-1.0, \"reason\": \"...\", \"tags\": [\"...\"]}}]}}"}
    ]
    # Görselleri işaretle
    for im in payload_images:
        user_content.append({
            "type": "image_url",
            "image_url": {
                "url": im["data_url"]
            }
        })
        # Takip eden text bloğu ile o görselin id’sini bildiriyoruz
        user_content.append({
            "type": "text",
            "text": f"id: {im['id']}"
        })

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system", "content": system_prompt},
                {"role":"user", "content": user_content}
            ],
            temperature=0.2,
            max_tokens=800,
        )
        content = resp.choices[0].message.content or "{}"
    except Exception as e:
        return jsonify({"error": f"OpenAI error: {str(e)}"}), 500

    # JSON parse
    try:
        parsed = json.loads(content)
        raw_matches = parsed.get("matches") or []
    except Exception:
        # Model JSON'u bozdiyse kaba düzeltme: hiç eşleşme yok
        raw_matches = []

    # id'yi eventId/photo'ya ayırıp, skor ve açıklamaları normalize et
    result_matches = []
    for m in raw_matches:
        _id = m.get("id") or ""
        if "::" not in _id:
            continue
        event_id, photo = _id.split("::", 1)
        score = float(m.get("score") or 0.0)
        reason = (m.get("reason") or "").strip()
        tags = m.get("tags") or []
        result_matches.append({
            "eventId": event_id,
            "photo": photo,
            "score": round(score, 3),
            "reason": reason[:140],
            "tags": tags[:6]
        })

    # Skora göre sırala (yüksekten düşüğe)
    result_matches.sort(key=lambda x: x["score"], reverse=True)

    return jsonify({"matches": result_matches})
    

if __name__ == "__main__":
    os.makedirs("templates", exist_ok=True)
    os.makedirs("static", exist_ok=True)
    app.run(host="0.0.0.0", port=5000, debug=True)
