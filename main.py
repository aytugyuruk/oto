import os
import yt_dlp
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime, timezone
import schedule
import time
import threading
from flask import Flask

# Ortam değişkenlerini yükle
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CHANNEL_URL = os.getenv("CHANNEL_URL")

# Supabase bağlantısını kurma
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("Supabase bağlantısı başarılı!")
except Exception as e:
    print(f"Supabase bağlantısı sırasında bir hata oluştu: {e}")
    exit(1)

app = Flask(__name__)

def upload_to_supabase(file_path):
    bucket_name = "audio"
    file_name = os.path.basename(file_path)
    try:
        with open(file_path, "rb") as f:
            response = supabase.storage.from_(bucket_name).upload(file_name, f.read(), {"content-type": "audio/mpeg"})
        print(f"Dosya {file_name} başarıyla yüklendi.")
        return True
    except Exception as e:
        print(f"Dosya yüklenirken hata oluştu: {e}")
        return False

def fetch_and_upload_today_video():
    print("Kontrol başladı:", datetime.now())
    
    # İlk olarak kanal videolarını listele
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'playlistend': 5,  # Sadece son 5 videoyu kontrol et
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Kanal kontrol ediliyor: {CHANNEL_URL}")
            info = ydl.extract_info(CHANNEL_URL, download=False)
            entries = info.get("entries", [])
            
            if not entries:
                print("Kanalda video bulunamadı.")
                return

            print(f"Kanal bilgileri alındı, {len(entries)} video bulundu")
            
            # Bugünün tarihini al
            today_str = datetime.now(timezone.utc).strftime('%Y%m%d')
            print(f"Bugünün tarihi: {today_str}")
            
            # En son videoyu kontrol et
            latest_video = entries[0]
            video_id = latest_video.get('id')
            video_title = latest_video.get('title', 'Bilinmeyen Başlık')
            
            print(f"Son video: {video_title} (ID: {video_id})")
            
            # Video detaylarını al
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            # Video detaylarını tam olarak çek
            detail_opts = {
                'quiet': True,
            }
            
            with yt_dlp.YoutubeDL(detail_opts) as ydl_detail:
                video_info = ydl_detail.extract_info(video_url, download=False)
                upload_date = video_info.get("upload_date")
                
                print(f"Video yükleme tarihi: {upload_date}")
                
                if not upload_date:
                    print("Upload tarihi alınamadı, işlem atlandı.")
                    return

                if upload_date != today_str:
                    print(f"Video bugün yüklenmemiş. Video tarihi: {upload_date}, Bugün: {today_str}")
                    return

                print("Bugün yüklenen video bulundu, indiriliyor...")

                # Ses dosyasını indir
                audio_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': 'downloads/%(title)s.%(ext)s',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'quiet': False,  # İndirme ilerlemesini göster
                }

                os.makedirs("downloads", exist_ok=True)

                try:
                    with yt_dlp.YoutubeDL(audio_opts) as ydl_audio:
                        print("Ses dosyası indiriliyor...")
                        ydl_audio.download([video_url])
                        print("İndirme tamamlandı.")
                except Exception as e:
                    print(f"Video indirme sırasında hata oluştu: {e}")
                    return

                # İndirilen dosyaları yükle
                uploaded_files = []
                downloads_dir = "downloads"
                
                if os.path.exists(downloads_dir):
                    for file in os.listdir(downloads_dir):
                        if file.endswith(".mp3"):
                            file_path = os.path.join(downloads_dir, file)
                            print(f"Dosya yükleniyor: {file}")
                            
                            if upload_to_supabase(file_path):
                                uploaded_files.append(file)
                                os.remove(file_path)
                                print(f"Dosya başarıyla yüklendi ve silindi: {file}")
                            else:
                                print(f"Dosya yüklenemedi: {file}")
                
                if uploaded_files:
                    print(f"Toplam {len(uploaded_files)} dosya başarıyla yüklendi.")
                else:
                    print("Hiçbir dosya yüklenemedi.")

    except Exception as e:
        print(f"Genel hata oluştu: {e}")
        import traceback
        traceback.print_exc()

# Manuel tetikleme için endpoint
@app.route("/run-now")
def run_now():
    try:
        print("Manuel tetikleme başlatıldı...")
        threading.Thread(target=fetch_and_upload_today_video).start()
        return "Video kontrolü ve yükleme işlemi başlatıldı. Konsol loglarını kontrol edin."
    except Exception as e:
        print(f"Manuel tetikleme sırasında hata oluştu: {e}")
        return f"Bir hata oluştu: {str(e)}"

# Test endpoint'i - sadece kanal bilgilerini göster
@app.route("/test-channel")
def test_channel():
    try:
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'playlistend': 3,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(CHANNEL_URL, download=False)
            entries = info.get("entries", [])
            
            result = f"Kanal: {info.get('title', 'Bilinmeyen')}<br><br>"
            result += f"Toplam video sayısı: {len(entries)}<br><br>"
            
            for i, entry in enumerate(entries[:3]):
                result += f"Video {i+1}: {entry.get('title', 'Başlık yok')}<br>"
                result += f"ID: {entry.get('id', 'ID yok')}<br>"
                result += f"URL: https://www.youtube.com/watch?v={entry.get('id', '')}<br><br>"
            
            return result
            
    except Exception as e:
        return f"Hata: {str(e)}"

# Başlangıç sayfası
@app.route("/")
def index():
    return """
    <h2>YouTube Ses Yükleyici Bot</h2>
    <p>Bot çalışıyor...</p>
    <a href="/test-channel">Kanal Testi</a><br>
    <a href="/run-now">Manuel Çalıştır</a>
    """

if __name__ == "__main__":
    try:
        print("Flask sunucusu başlatılıyor...")
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)), debug=True)
    except Exception as e:
        print(f"Flask sunucusu başlatılırken hata oluştu: {e}")
