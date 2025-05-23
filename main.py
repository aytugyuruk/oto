import os
import shutil
import random
import yt_dlp
from supabase import create_client, Client
from dotenv import load_dotenv
import pytz
from datetime import datetime, time
import schedule
import time as time_module

# --- Yapılandırma ---
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CHANNEL_URL = os.getenv("CHANNEL_URL")
DOWNLOAD_DIR = "ses_indirmeleri"
BUCKET_NAME = "audio"

# --- Supabase İstemcisi ---
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✓ Supabase bağlantısı başarılı")
except Exception as e:
    print(f"✗ Supabase bağlantı hatası: {str(e)}")
    exit(1)

# --- Yardımcı Fonksiyonlar ---
def sanitize_filename(title: str) -> str:
    """Güvenli dosya adı oluşturur"""
    return "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in title).strip()

def check_cookies():
    """Çerez dosyasını kontrol eder"""
    if not os.path.exists("cookies.txt"):
        print("⚠️ Uyarı: cookies.txt bulunamadı (login gereken içeriklerde sorun çıkabilir)")
        return False
    return True

# --- Ana Fonksiyonlar ---
def get_latest_video_info(channel_url: str) -> dict | None:
    """Kanalın son videosunu alır"""
    ydl_opts = {
        'extract_flat': True,
        'playlistend': 1,
        'quiet': True,
        'ignoreerrors': True,
        'cookiefile': 'cookies.txt' if check_cookies() else None
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
            if not info or 'entries' not in info:
                print("ⓘ Kanalda video bulunamadı veya erişim engellendi")
                return None

            video = info['entries'][0]
            video_id = video.get('id')
            video_url = f"https://youtu.be/{video_id}" if video_id else video.get('url')
            
            if not video_url:
                print("✗ Video URL'si alınamadı")
                return None

            return {
                'title': video.get('title', 'Bilinmeyen Başlık'),
                'url': video_url,
                'id': video_id
            }
    except Exception as e:
        print(f"✗ Video bilgisi alınamadı: {str(e)}")
        return None

def download_video_audio(video_url: str, video_title: str) -> str | None:
    """Videoyu MP3 olarak indirir"""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    safe_title = sanitize_filename(video_title)
    output_path = os.path.join(DOWNLOAD_DIR, f"{safe_title}.%(ext)s")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'retries': 3,
        'cookiefile': 'cookies.txt' if check_cookies() else None,
        'http_headers': {
            'User-Agent': random.choice([
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            ]),
            'Accept-Language': 'en-US,en;q=0.9'
        },
        'age_limit': 18,
        'ignoreerrors': False
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
            
        for file in os.listdir(DOWNLOAD_DIR):
            if file.startswith(safe_title) and file.endswith('.mp3'):
                return os.path.join(DOWNLOAD_DIR, file)
                
        print("✗ İndirilen dosya bulunamadı")
        return None
    except Exception as e:
        print(f"✗ İndirme hatası: {str(e)}")
        return None

def upload_to_supabase(file_path: str) -> bool:
    try:
        with open(file_path, 'rb') as f:
            supabase.storage.from_(BUCKET_NAME).upload(
                path=os.path.basename(file_path),
                file=f,
                file_options={
                    'content-type': 'audio/mpeg',
                    'upsert': 'true'
                }
            )
        return True
    except Exception as e:
        print(f"✗ Supabase yükleme hatası: {str(e)}")
        return False

def cleanup():
    """Geçici dosyaları temizler"""
    if os.path.exists(DOWNLOAD_DIR):
        shutil.rmtree(DOWNLOAD_DIR)
        print("🗑️ İndirme klasörü temizlendi")

def run_pipeline():
    print("\n" + "="*50)
    print(f"YouTube → Supabase Audio Pipeline - {datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50 + "\n")

    if not all([SUPABASE_URL, SUPABASE_KEY, CHANNEL_URL]):
        print("✗ Ortam değişkenleri eksik! .env dosyasını kontrol edin")
        return

    # 1. Son videoyu al
    if not (video := get_latest_video_info(CHANNEL_URL)):
        return

    print(f"🔍 Bulunan video: {video['title']}")

    # 2. Ses dosyasını indir
    if not (audio_path := download_video_audio(video['url'], video['title'])):
        cleanup()
        return

    # 3. Supabase'e yükle
    if not upload_to_supabase(audio_path):
        cleanup()
        return

    # 4. Temizlik
    cleanup()
    print("\n✅ İşlem tamamlandı\n")

def schedule_job():
    # Turkey Time (UTC+3)
    turkey_time = pytz.timezone('Europe/Istanbul')
    
    # Schedule daily at 20:00 Turkey Time
    schedule.every().day.at("20:00", timezone=turkey_time).do(run_pipeline)
    
    print("Scheduler started. Waiting for 20:00 Turkey Time...")
    
    while True:
        schedule.run_pending()
        time_module.sleep(60)  # Check every minute

if __name__ == "__main__":
    # For Render.com, we'll use the scheduler
    schedule_job()
