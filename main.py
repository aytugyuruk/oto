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
            if response.status_code == 200:
                print(f"Dosya {file_name} başarıyla yüklendi.")
            else:
                print(f"Yükleme sırasında bir hata oluştu: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Dosya yüklenirken hata oluştu: {e}")

def fetch_and_upload_today_video():
    print("Kontrol başladı:", datetime.now())
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'force_generic_extractor': True,
        'skip_download': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(CHANNEL_URL, download=False)
            entries = info.get("entries", [])
            if not entries:
                print("Kanalda video bulunamadı.")
                return

            latest_video = entries[0]
            upload_date = latest_video.get("upload_date")  # Format: YYYYMMDD

            if not upload_date:
                print("Upload tarihi alınamadı, işlem atlandı.")
                return

            today_str = datetime.now(timezone.utc).strftime('%Y%m%d')
            if upload_date != today_str:
                print("Bugün yeni video yüklenmemiş.")
                return

            video_url = latest_video.get('url', None)
            if not video_url:
                print("Video URL'si alınamadı, işlem atlandı.")
                return

            print("Bugün yüklenen video bulundu:", latest_video["title"])

            audio_opts = {
                'format': 'bestaudio/best',
                'outtmpl': 'downloads/%(title)s.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                }]
            }

            os.makedirs("downloads", exist_ok=True)

            try:
                with yt_dlp.YoutubeDL(audio_opts) as ydl2:
                    ydl2.download([f"https://www.youtube.com/watch?v={video_url}"])
            except Exception as e:
                print(f"Video indirme sırasında hata oluştu: {e}")
                return

            for file in os.listdir("downloads"):
                if file.endswith(".mp3"):
                    file_path = os.path.join("downloads", file)
                    upload_to_supabase(file_path)
                    print("Yüklendi:", file)
                    os.remove(file_path)

    except Exception as e:
        print(f"Genel hata oluştu: {e}")

# Manuel tetikleme için endpoint
@app.route("/run-now")
def run_now():
    try:
        threading.Thread(target=fetch_and_upload_today_video).start()
        return "Video kontrolü ve yükleme işlemi başlatıldı."
    except Exception as e:
        print(f"Manuel tetikleme sırasında hata oluştu: {e}")
        return "Bir hata oluştu, lütfen tekrar deneyin."

# Başlangıç sayfası
@app.route("/")
def index():
    return "YouTube Ses Yükleyici Bot çalışıyor..."

if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=8000)
    except Exception as e:
        print(f"Flask sunucusu başlatılırken hata oluştu: {e}")
