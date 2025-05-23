import os
import shutil
import random
import yt_dlp
import time
import schedule
import datetime
import pytz
from supabase import create_client, Client
from dotenv import load_dotenv

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
        'age_limit': 18,  # Yaş sınırlı içerikler için
        'ignoreerrors': False  # Hataları göster
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
            
        # İndirilen dosyayı bul
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
                    'upsert': 'true'  # DÜZELTME: True -> 'true'
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

# --- Ana Görev Fonksiyonu ---
def run_pipeline():
    if not all([SUPABASE_URL, SUPABASE_KEY, CHANNEL_URL]):
        print("✗ Ortam değişkenleri eksik! .env dosyasını kontrol edin")
        return

    print("\n" + "="*50)
    print("YouTube → Supabase Audio Pipeline")
    print("="*50 + "\n")
    
    # Şu anki zamanı yazdır
    istanbul_tz = pytz.timezone('Europe/Istanbul')
    now = datetime.datetime.now(istanbul_tz)
    print(f"📅 Çalışma zamanı: {now.strftime('%Y-%m-%d %H:%M:%S')} (İstanbul)")

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

# --- Ana İşlem ---
if __name__ == "__main__":
    print("🕒 YouTube → Supabase Audio Pipeline Zamanlanmış Görev")
    print(f"📌 Her gün İstanbul saatiyle 20:00'de çalışacak şekilde ayarlandı")
    
    # İstanbul saat dilimine göre 20:00'de çalışacak şekilde zamanla
    schedule.every().day.at("20:00").do(run_pipeline)
    
    # Bir defa şimdi çalıştırmak isterseniz, aşağıdaki satırı yorum işaretinden kurtarın
    # run_pipeline()
    
    # Programı çalışır durumda tut ve zamanı kontrol et
    while True:
        schedule.run_pending()
        time.sleep(60)  # Her dakika zamanı kontrol et
