import os
import yt_dlp
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime, timezone
import schedule
import time
import threading
from flask import Flask
import random

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

def get_common_ydl_opts():
    """Bot korumasından kaçınmak için ortak ayarlar"""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    ]
    
    return {
        'http_headers': {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Accept-Encoding': 'gzip,deflate',
            'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
            'Keep-Alive': '300',
            'Connection': 'keep-alive',
        },
        'sleep_interval': 2,
        'max_sleep_interval': 5,
        'sleep_interval_requests': 1,
        'retries': 3,
        'fragment_retries': 3,
        'extractor_retries': 3,
        'file_access_retries': 3,
        'socket_timeout': 30,
    }

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
    
    # Bot korumasından kaçınmak için ek ayarlar
    base_opts = get_common_ydl_opts()
    ydl_opts = {
        **base_opts,
        'quiet': True,
        'extract_flat': True,
        'playlistend': 5,
        'no_warnings': True,
        'ignoreerrors': True,
    }

    try:
        print(f"Kanal kontrol ediliyor: {CHANNEL_URL}")
        
        # Rastgele bekleme ekle
        time.sleep(random.uniform(1, 3))
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(CHANNEL_URL, download=False)
            except Exception as e:
                print(f"Kanal bilgileri alınamadı: {e}")
                # RSS feed alternatifi dene
                return try_rss_fallback()
            
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
            
            # Video URL'sini oluştur
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            # Bot korumasından kaçınmak için bekleme
            time.sleep(random.uniform(2, 4))
            
            # Video detaylarını almak için daha güvenli yöntem
            detail_opts = {
                **base_opts,
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'skip_download': True,
            }
            
            try:
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
                    
                    # İndirme işlemi
                    return download_audio(video_url, video_title)
                    
            except Exception as e:
                print(f"Video detayları alınamadı: {e}")
                # Tarihi kontrol etmeden direkt indirmeyi dene
                print("Tarihi kontrol etmeden indirme deneniyor...")
                return download_audio(video_url, video_title)

    except Exception as e:
        print(f"Genel hata oluştu: {e}")
        import traceback
        traceback.print_exc()

def try_rss_fallback():
    """RSS feed ile alternatif yöntem"""
    try:
        print("RSS feed alternatifi deneniyor...")
        # YouTube kanalının RSS feed URL'sini oluştur
        if "/channel/" in CHANNEL_URL:
            channel_id = CHANNEL_URL.split("/channel/")[1].split("/")[0]
        elif "/@" in CHANNEL_URL:
            # @username formatından channel ID'ye çevirmek daha karmaşık
            print("@username formatı için RSS feed desteği sınırlı")
            return False
        else:
            print("Kanal URL formatı tanınamadı")
            return False
            
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        
        # RSS feed'i işle (basit implementasyon)
        import urllib.request
        import xml.etree.ElementTree as ET
        
        with urllib.request.urlopen(rss_url) as response:
            rss_data = response.read()
            
        root = ET.fromstring(rss_data)
        
        # İlk video entry'sini al
        entry = root.find('.//{http://www.w3.org/2005/Atom}entry')
        if entry is not None:
            video_id = entry.find('.//{http://www.youtube.com/xml/schemas/2015}videoId').text
            title = entry.find('.//{http://www.w3.org/2005/Atom}title').text
            published = entry.find('.//{http://www.w3.org/2005/Atom}published').text
            
            # Tarihi kontrol et
            pub_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
            today = datetime.now(timezone.utc)
            
            if pub_date.date() == today.date():
                print(f"RSS'den bugünün videosu bulundu: {title}")
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                return download_audio(video_url, title)
            else:
                print("RSS'de bugünün videosu bulunamadı")
                return False
        
    except Exception as e:
        print(f"RSS alternatifi başarısız: {e}")
        return False

def download_audio(video_url, video_title):
    """Ses dosyasını indir ve yükle"""
    try:
        # Ses indirme için ayarlar
        base_opts = get_common_ydl_opts()
        audio_opts = {
            **base_opts,
            'format': 'bestaudio/best',
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': False,
            'no_warnings': False,
        }

        os.makedirs("downloads", exist_ok=True)
        
        # Bot korumasından kaçınmak için bekleme
        time.sleep(random.uniform(3, 6))

        try:
            with yt_dlp.YoutubeDL(audio_opts) as ydl_audio:
                print("Ses dosyası indiriliyor...")
                ydl_audio.download([video_url])
                print("İndirme tamamlandı.")
        except Exception as e:
            print(f"Video indirme sırasında hata oluştu: {e}")
            return False

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
            return True
        else:
            print("Hiçbir dosya yüklenemedi.")
            return False
            
    except Exception as e:
        print(f"İndirme işlemi sırasında hata: {e}")
        return False

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

# Test endpoint'i - sadece kanal bilgilerini göster (güvenli mod)
@app.route("/test-channel")
def test_channel():
    try:
        # RSS feed ile test et
        if "/channel/" in CHANNEL_URL:
            channel_id = CHANNEL_URL.split("/channel/")[1].split("/")[0]
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            
            import urllib.request
            import xml.etree.ElementTree as ET
            
            with urllib.request.urlopen(rss_url) as response:
                rss_data = response.read()
                
            root = ET.fromstring(rss_data)
            
            result = f"Kanal: {root.find('.//{http://www.w3.org/2005/Atom}title').text}<br><br>"
            
            entries = root.findall('.//{http://www.w3.org/2005/Atom}entry')[:3]
            result += f"Son {len(entries)} video:<br><br>"
            
            for i, entry in enumerate(entries):
                title = entry.find('.//{http://www.w3.org/2005/Atom}title').text
                video_id = entry.find('.//{http://www.youtube.com/xml/schemas/2015}videoId').text
                published = entry.find('.//{http://www.w3.org/2005/Atom}published').text
                
                result += f"Video {i+1}: {title}<br>"
                result += f"ID: {video_id}<br>"
                result += f"Yayın tarihi: {published}<br><br>"
            
            return result
        else:
            return "RSS feed için channel ID formatı gerekli (/@username desteklenmiyor)"
            
    except Exception as e:
        return f"Test hatası: {str(e)}"

# Başlangıç sayfası
@app.route("/")
def index():
    return """
    <h2>YouTube Ses Yükleyici Bot</h2>
    <p>Bot çalışıyor... (Bot koruması optimizasyonlu)</p>
    <a href="/test-channel">Kanal Testi (RSS)</a><br>
    <a href="/run-now">Manuel Çalıştır</a>
    """

if __name__ == "__main__":
    try:
        print("Flask sunucusu başlatılıyor...")
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)), debug=True)
    except Exception as e:
        print(f"Flask sunucusu başlatılırken hata oluştu: {e}")
