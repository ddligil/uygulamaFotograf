# face_engine.py
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple
import numpy as np
import face_recognition

# -----------------------------
# Ayarlar
# -----------------------------
# Yüz tespiti modeli: "hog" (CPU-dostu) veya "cnn" (daha iyi, CUDA gerekebilir)
FACE_LOC_MODEL = "hog"   # istersen "cnn" yap
# Varsayılan upsample: küçük yüzleri yakalamak için 1 iyi başlangıç
FACE_LOC_UPSAMPLE = 1
# Fotoğraftaki çok küçük yüzleri elemek için minimum yüz kenar uzunluğu (piksel)
MIN_FACE_SIZE_PX = 60

# -----------------------------
# Yol kurulumu (mutlak & güvenli)
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EVENTS_DIR = DATA_DIR / "events"
USERS_DIR = DATA_DIR / "users"

def _ensure_dir_is_directory(p: Path):
    """Yol var ve dosyaysa .bak yap; yoksa klasör oluştur."""
    if p.exists() and p.is_file():
        p.rename(p.with_suffix(p.suffix + ".bak"))
    p.mkdir(parents=True, exist_ok=True)

_ensure_dir_is_directory(DATA_DIR)
_ensure_dir_is_directory(EVENTS_DIR)
_ensure_dir_is_directory(USERS_DIR)

def ensure_event_dirs(event_id: str) -> Tuple[str, str]:
    """
    event klasörlerini oluşturur: {event_id}/photos, encodings.json
    Dönen: (photos_dir_path_str, encodings_json_path_str)
    """
    e_dir = EVENTS_DIR / event_id
    photos_dir = e_dir / "photos"
    _ensure_dir_is_directory(e_dir)
    _ensure_dir_is_directory(photos_dir)

    enc_path = e_dir / "encodings.json"
    if not enc_path.exists():
        enc_path.write_text("{}", encoding="utf-8")

    return str(photos_dir), str(enc_path)

# -----------------------------
# JSON yardımcıları
# -----------------------------
def load_json(path: str, default):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default

def save_json(path: str, obj: Any):
    p = Path(path)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

# -----------------------------
# Yüz kodlama
# -----------------------------
def _filter_small_boxes(boxes: list[tuple[int, int, int, int]], min_size_px: int) -> list[tuple[int, int, int, int]]:
    """face_recognition.face_locations kutularını (top, right, bottom, left) küçük yüzleri eleyerek döndürür."""
    filtered = []
    for (top, right, bottom, left) in boxes:
        h = bottom - top
        w = right - left
        if h >= min_size_px and w >= min_size_px:
            filtered.append((top, right, bottom, left))
    return filtered

def _encodings_from_image_array(img: np.ndarray, upsample: int, min_size_px: int) -> List[List[float]]:
    boxes = face_recognition.face_locations(img, model=FACE_LOC_MODEL, number_of_times_to_upsample=upsample)
    boxes = _filter_small_boxes(boxes, min_size_px)
    if not boxes:
        return []
    # Use face_encodings without parameters - this version doesn't support known_face_locations
    try:
        encs = face_recognition.face_encodings(img)
    except Exception as e:
        print(f"Face encoding failed: {e}")
        return []
    return [enc.tolist() for enc in encs]

def image_to_encodings(img_path: str, deep: bool = False) -> List[List[float]]:
    """
    Resimdeki TÜM yüzleri kodlar (128-d encodings).
    deep=True: upsample artırılır, min yüz boyutu biraz düşürülür.
    """
    img = face_recognition.load_image_file(img_path)
    up = FACE_LOC_UPSAMPLE + (1 if deep else 0)
    min_px = max(40, MIN_FACE_SIZE_PX - (10 if deep else 0))
    return _encodings_from_image_array(img, upsample=up, min_size_px=min_px)

def add_event_photo(event_id: str, saved_path: str):
    """Foto eklendiğinde yüz kodlarını günceller (tüm yüzler)."""
    photos_dir, enc_path = ensure_event_dirs(event_id)
    enc_map = load_json(enc_path, {})
    rel_name = Path(saved_path).name
    encs = image_to_encodings(saved_path)
    enc_map[rel_name] = encs  # bir foto içinde birden fazla yüz olabilir
    save_json(enc_path, enc_map)

def _query_encodings_with_augmentations(image_path: str, deep: bool = False) -> List[np.ndarray]:
    """
    Sorgu için augmentasyonlu encoding listesi döndürür:
    - Orijinal
    - Yatay çevrilmiş (flip)
    (İleriye dönük: parlaklık/kontrast varyasyonları eklenebilir)
    """
    img = face_recognition.load_image_file(image_path)
    up = FACE_LOC_UPSAMPLE + (1 if deep else 0)
    min_px = max(40, MIN_FACE_SIZE_PX - (10 if deep else 0))

    encs = _encodings_from_image_array(img, upsample=up, min_size_px=min_px)
    res = [np.array(e, dtype=np.float32) for e in encs]

    # Flip (yatay)
    flipped = np.fliplr(img)
    encs_flip = _encodings_from_image_array(flipped, upsample=up, min_size_px=min_px)
    res.extend(np.array(e, dtype=np.float32) for e in encs_flip)

    # Çok yüz varsa, ilk(ler) öncelik — fakat hepsini tutmak da faydalı.
    return res

def encode_single_face(image_path: str) -> List[float] | None:
    """Geriye dönük uyumluluk için (kullanılmıyor ama dursun)."""
    encs = image_to_encodings(image_path)
    if not encs:
        return None
    return encs[0]

# -----------------------------
# Eşleştirme (Euclidean distance)
# -----------------------------
def _face_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))

def find_matches(event_id: str, query_face_path: str | List[str], threshold: float = 0.60, deep: bool = False) -> List[Dict[str, Any]]:
    """
    Euclidean distance ile eşleştirme.
    - threshold: DÜŞÜK değer daha katı (default 0.60).
    - deep=True: daha hassas tespit (yavaş).
    - query_face_path: tek yol ya da birden çok selfie yolu listesi.
    Dönen: [{"photo": foto_adı, "score": en_iyi_uyum_mesafesi}, ...], score küçükten büyüğe sıralı
    """
    # Sorgu enc'lerini hazırla (augmentasyonla)
    query_paths = query_face_path if isinstance(query_face_path, list) else [query_face_path]
    q_encs: List[np.ndarray] = []
    for qp in query_paths:
        q_encs.extend(_query_encodings_with_augmentations(qp, deep=deep))
    if not q_encs:
        return []

    # Event encodings'i yükle
    _, enc_path = ensure_event_dirs(event_id)
    enc_map = load_json(enc_path, {})

    results = []
    for photo_name, enc_list in enc_map.items():
        if not enc_list:
            continue
        best = 10.0  # büyükten başla
        # Foto içindeki tüm yüz enc'leri ile Tüm sorgu enc'leri arasında en küçük mesafe
        for enc in enc_list:
            e = np.array(enc, dtype=np.float32)
            for q in q_encs:
                d = _face_distance(q, e)
                if d < best:
                    best = d
        if best <= threshold:
            results.append({"photo": photo_name, "score": round(best, 3)})

    results.sort(key=lambda x: x["score"])  # küçük daha iyi
    return results
