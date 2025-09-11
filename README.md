# UygulamaFotoğraf - AI-Powered Photo Management System

Bu proje, yüz tanıma teknolojisi ve AI destekli görsel arama ile fotoğraf yönetimi sağlayan bir Flask web uygulamasıdır.

## 🚀 Özellikler

### 📸 Fotoğraf Yönetimi
- **Yüz Tanıma**: `face_recognition` kütüphanesi ile otomatik yüz algılama
- **Event Sistemi**: Fotoğrafları etkinliklere göre gruplama
- **Benzerlik Arama**: Yüz benzerliği ile fotoğraf arama

### 🤖 AI Destekli Sanal Albüm
- **Sanal Albüm**: Favori fotoğrafları toplama ve organize etme
- **AI Görsel Arama**: OpenAI GPT-4 Vision ile doğal dil arama
- **Klasör Sistemi**: Fotoğrafları klasörlere ayırma
- **Filtreleme**: İsim bazlı arama ve filtreleme

### 💻 Teknik Özellikler
- **Flask Web Framework**: Modern web arayüzü
- **Bootstrap UI**: Responsive tasarım
- **JSON Storage**: Dosya tabanlı veri saklama
- **Drag & Drop**: Fotoğraf yükleme için sürükle-bırak

## 🛠️ Kurulum

### Gereksinimler
```bash
pip install flask face_recognition pillow numpy werkzeug openai
```

### Çalıştırma
```bash
python app.py
```

Uygulama `http://localhost:5000` adresinde çalışacaktır.

## 📁 Proje Yapısı

```
├── app.py              # Ana Flask uygulaması
├── face_engine.py      # Yüz tanıma motoru
├── templates/          # HTML şablonları
│   ├── index.html     # Ana sayfa
│   └── album.html      # Sanal albüm sayfası
├── static/            # CSS/JS dosyaları
├── data/              # Fotoğraf ve veri saklama
│   ├── events/        # Event fotoğrafları
│   └── users/         # Kullanıcı fotoğrafları
└── storage.json       # Uygulama verisi
```

## 🎯 Kullanım

1. **Event Oluşturma**: Ana sayfadan yeni etkinlik oluşturun
2. **Fotoğraf Yükleme**: Event'e fotoğraf yükleyin
3. **Arama**: Yüz benzerliği ile fotoğraf arayın
4. **Sanal Albüm**: Favori fotoğrafları albüme ekleyin
5. **AI Arama**: Doğal dil ile fotoğraf arayın ("güneş gözlüğü", "daha genç" vb.)

## 🔧 API Endpoints

- `POST /event/create` - Yeni event oluşturma
- `POST /event/{id}/upload` - Fotoğraf yükleme
- `POST /search` - Yüz benzerliği arama
- `POST /api/album_ai_query` - AI görsel arama
- `GET /album` - Sanal albüm sayfası

## 📝 Notlar

- OpenAI API anahtarı gereklidir (AI arama için)
- Fotoğraflar `data/` klasöründe saklanır
- Yüz encodings JSON formatında cache'lenir

## 🐛 Bilinen Sorunlar

- AI arama bazen "eşleşme bulunamadı" döndürebilir
- Büyük fotoğraf dosyaları yavaş işlenebilir
- `malloc: double free` hatası ara sıra görülebilir

## 📄 Lisans

Bu proje MIT lisansı altında lisanslanmıştır.
