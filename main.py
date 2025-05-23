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

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)

def upload_to_supabase(file_path):
    bucket_name = "audio"
    file_name = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        supabase.storage.from_(bucket_name).upload(file_name, f.read(), {"content-type": "audio/mpeg"})

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

            video_url = latest_video['url']
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

            with yt_dlp.YoutubeDL(audio_opts) as ydl2:
                ydl2.download([f"https://www.youtube.com/watch?v={video_url}"])

            for file in os.listdir("downloads"):
                if file.endswith(".mp3"):
                    file_path = os.path.join("downloads", file)
                    upload_to_supabase(file_path)
                    print("Yüklendi:", file)
                    os.remove(file_path)

    except Exception as e:
        print("Hata oluştu:", e)

def run_schedule():
    # Türkiye saati 20:00 → UTC 17:00
    schedule.every().day.at("17:00").do(fetch_and_upload_today_video)
    while True:
        schedule.run_pending()
        time.sleep(30)

@app.route("/")
def index():
    return "YouTube Ses Yükleyici Bot çalışıyor..."

if __name__ == "__main__":
    thread = threading.Thread(target=run_schedule)
    thread.daemon = True
    thread.start()
    # Render için portu 8000 olarak açıyoruz
    app.run(host="0.0.0.0", port=8000)