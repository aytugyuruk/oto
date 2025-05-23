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
import json
import subprocess

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

def get_cookies_path():
    """Cookie dosyasının yolunu döndür"""
    return os.path.join(os.getcwd(), "youtube_cookies.txt")

def extract_cookies_from_browser():
    """Tarayıcıdan cookie'leri çıkar"""
    try:
        cookies_path = get_cookies_path()
        
        # Chrome'dan cookie'leri çıkarmayı dene
        result = subprocess.run([
            'yt-dlp', 
            '--cookies-from-browser', 'chrome',
            '--cookies', cookies_path,
            '--skip-download',
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ'  # test video
        ], capture_output=True, text=True, timeout=30)
        
        if os.path.exists(cookies_path):
            print("Chrome'dan cookie'ler başarıyla çıkarıldı!")
            return cookies_path
        
        # Firefox'tan dene
        result = subprocess.run([
            'yt-dlp', 
            '--cookies-from-browser', 'firefox',
            '--cookies', cookies_path,
            '--skip-download',
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
        ], capture_output=True, text=True, timeout=30)
        
        if os.path.exists(cookies_path):
            print("Firefox'tan cookie'ler başarıyla çıkarıldı!")
            return cookies_path
            
    except Exception as e:
        print(f"Cookie çıkarma hatası: {e}")
    
    return None

def get_robust_ydl_opts(use_cookies=True):
    """Bot korumasından kaçınmak için güçlü ayarlar"""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ]
    
    opts = {
        'http_headers': {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        },
        'sleep_interval': 3,
        'max_sleep_interval': 8,
        'sleep_interval_requests': 2,
        'retries': 5,
        'fragment_retries': 5,
        'extractor_retries': 5,
        'file_access_retries': 5,
        'socket_timeout': 60,
        'ignoreerrors': True,
        'no_warnings': True,
        'extract_flat': False,  # Tam bilgi almak için
        'writeinfojson': False,
        'writethumbnail': False,
        'writesubtitles': False,
        'writeautomaticsub': False,
    }
    
    # Cookie kullan
    if use_cookies:
        cookies_path = get_cookies_path()
        if os.path.exists(cookies_path):
            opts['cookiefile'] = cookies_path
            print("Cookie dosyası kullanılıyor...")
        else:
            print("Cookie dosyası bulunamadı, otomatik çıkarma deneniyor...")
            extracted_cookies = extract_cookies_from_browser()
            if extracted_cookies:
                opts['cookiefile'] = extracted_cookies
    
    return opts

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

def try_alternative_extractors(video_url):
    """Alternatif extractor'ları dene"""
    extractors = [
        {'ie_key': 'Youtube', 'format': 'bestaudio/best'},
        {'ie_key': 'YoutubeTab', 'format': 'bestaudio/best'},
        {'ie_key': 'Generic', 'format': 'best'},
    ]
    
    for extractor in extractors:
        try:
            print(f"Alternatif extractor deneniyor: {extractor['ie_key']}")
            opts = get_robust_ydl_opts(use_cookies=True)
            opts.update({
                'format': extractor['format'],
                'outtmpl': 'downloads/%(title)s.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
            
            time.sleep(random.uniform(5, 10))  # Uzun bekleme
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([video_url])
                return True
                
        except Exception as e:
            print(f"Extractor {extractor['ie_key']} başarısız: {e}")
            continue
    
    return False

def get_video_from_rss():
    """RSS feed'den video bilgilerini al"""
    try:
        print("RSS feed kullanılıyor...")
        
        # Kanal ID'sini çıkar
        if "/channel/" in CHANNEL_URL:
            channel_id = CHANNEL_URL.split("/channel/")[1].split("/")[0]
        elif "/@" in CHANNEL_URL:
            # @username için channel ID bulma (basit yöntem)
            username = CHANNEL_URL.split("/@")[1].split("/")[0]
            print(f"Username: {username}")
            
            # Username'den channel ID'ye çevirme (bu kısım karmaşık, RSS direct çalışmayabilir)
            # Bu durumda direkt username ile deneyeceğiz
            return try_username_approach(username)
        else:
            print("Kanal URL formatı tanınamadı")
            return None
            
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        print(f"RSS URL: {rss_url}")
        
        import urllib.request
        import xml.etree.ElementTree as ET
        
        req = urllib.request.Request(rss_url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        with urllib.request.urlopen(req, timeout=30) as response:
            rss_data = response.read()
            
        root = ET.fromstring(rss_data)
        
        # İlk video entry'sini al
        entry = root.find('.//{http://www.w3.org/2005/Atom}entry')
        if entry is not None:
            video_id = entry.find('.//{http://www.youtube.com/xml/schemas/2015}videoId').text
            title = entry.find('.//{http://www.w3.org/2005/Atom}title').text
            published = entry.find('.//{http://www.w3.org/2005/Atom}published').text
            
            print(f"RSS'den video bulundu: {title}")
            print(f"Video ID: {video_id}")
            print(f"Yayın tarihi: {published}")
            
            # Tarihi kontrol et
            pub_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
            today = datetime.now(timezone.utc)
            
            if pub_date.date() == today.date():
                print("Video bugün yayınlanmış!")
                return {
                    'id': video_id,
                    'title': title,
                    'url': f"https://www.youtube.com/watch?v={video_id}",
                    'upload_date': pub_date.strftime('%Y%m%d')
                }
            else:
                print(f"Video bugün değil: {pub_date.date()} vs {today.date()}")
                return None
        
    except Exception as e:
        print(f"RSS hatası: {e}")
        return None

def try_username_approach(username):
    """Username ile direkt deneme"""
    try:
        # YouTube'da username ile arama
        search_url = f"https://www.youtube.com/@{username}/videos"
        print(f"Username URL'si: {search_url}")
        
        # Bu kısım daha karmaşık, şimdilik None döndür
        return None
        
    except Exception as e:
        print(f"Username yaklaşımı hatası: {e}")
        return None

def fetch_and_upload_today_video():
    print("Kontrol başladı:", datetime.now())
    
    # Önce RSS ile dene
    video_info = get_video_from_rss()
    
    if not video_info:
        print("RSS'den video bulunamadı veya bugün yayınlanmamış")
        return False
    
    video_url = video_info['url']
    video_title = video_info['title']
    
    print(f"İndirilecek video: {video_title}")
    print(f"Video URL: {video_url}")
    
    # İndirmeyi dene
    os.makedirs("downloads", exist_ok=True)
    
    # Önce standart yöntemle dene
    if download_with_standard_method(video_url):
        return upload_downloaded_files()
    
    # Alternatif extractor'larla dene
    print("Standart yöntem başarısız, alternatifler deneniyor...")
    if try_alternative_extractors(video_url):
        return upload_downloaded_files()
    
    # youtube-dl ile dene (son çare)
    print("yt-dlp başarısız, youtube-dl deneniyor...")
    if try_youtube_dl_fallback(video_url):
        return upload_downloaded_files()
    
    print("Tüm yöntemler başarısız oldu")
    return False

def download_with_standard_method(video_url):
    """Standart indirme yöntemi"""
    try:
        opts = get_robust_ydl_opts(use_cookies=True)
        opts.update({
            'format': 'bestaudio/best',
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': False,
        })
        
        time.sleep(random.uniform(3, 7))
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            print("Standart yöntemle indiriliyor...")
            ydl.download([video_url])
            return True
            
    except Exception as e:
        print(f"Standart indirme hatası: {e}")
        return False

def try_youtube_dl_fallback(video_url):
    """youtube-dl ile son deneme"""
    try:
        print("youtube-dl ile deneniyor...")
        
        cmd = [
            'youtube-dl',
            '--extract-audio',
            '--audio-format', 'mp3',
            '--audio-quality', '192K',
            '--output', 'downloads/%(title)s.%(ext)s',
            video_url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            print("youtube-dl ile başarılı!")
            return True
        else:
            print(f"youtube-dl hatası: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"youtube-dl fallback hatası: {e}")
        return False

def upload_downloaded_files():
    """İndirilen dosyaları yükle"""
    uploaded_files = []
    downloads_dir = "downloads"
    
    if os.path.exists(downloads_dir):
        for file in os.listdir(downloads_dir):
            if file.endswith((".mp3", ".m4a", ".webm", ".ogg")):
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

# Flask endpoint'leri
@app.route("/run-now")
def run_now():
    try:
        print("Manuel tetikleme başlatıldı...")
        result = threading.Thread(target=fetch_and_upload_today_video)
        result.start()
        return "Video kontrolü ve yükleme işlemi başlatıldı. Konsol loglarını kontrol edin."
    except Exception as e:
        print(f"Manuel tetikleme sırasında hata oluştu: {e}")
        return f"Bir hata oluştu: {str(e)}"

@app.route("/test-rss")
def test_rss():
    try:
        video_info = get_video_from_rss()
        if video_info:
            return f"""
            <h3>RSS Test Sonucu:</h3>
            <b>Başlık:</b> {video_info['title']}<br>
            <b>Video ID:</b> {video_info['id']}<br>
            <b>URL:</b> <a href="{video_info['url']}">{video_info['url']}</a><br>
            <b>Yükleme Tarihi:</b> {video_info['upload_date']}<br>
            """
        else:
            return "RSS'den bugünün videosu bulunamadı"
    except Exception as e:
        return f"RSS test hatası: {str(e)}"

@app.route("/setup-cookies")
def setup_cookies():
    try:
        cookies_path = extract_cookies_from_browser()
        if cookies_path:
            return f"Cookie'ler başarıyla çıkarıldı: {cookies_path}"
        else:
            return """
            Cookie çıkarılamadı. Manuel olarak şunları yapabilirsiniz:<br><br>
            1. Tarayıcınızda YouTube'a giriş yapın<br>
            2. Şu komutu çalıştırın:<br>
            <code>yt-dlp --cookies-from-browser chrome --cookies youtube_cookies.txt --skip-download https://www.youtube.com/watch?v=dQw4w9WgXcQ</code><br>
            3. youtube_cookies.txt dosyasının oluştuğunu kontrol edin
            """
    except Exception as e:
        return f"Cookie setup hatası: {str(e)}"

@app.route("/")
def index():
    return """
    <h2>YouTube Ses Yükleyici Bot (Gelişmiş)</h2>
    <p>Bot çalışıyor... (RSS + Cookie destekli)</p>
    <a href="/test-rss">RSS Testi</a><br>
    <a href="/setup-cookies">Cookie Kurulumu</a><br>
    <a href="/run-now">Manuel Çalıştır</a>
    """

if __name__ == "__main__":
    try:
        print("Flask sunucusu başlatılıyor...")
        print("YouTube bot koruması için RSS ve cookie desteği aktif")
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)), debug=True)
    except Exception as e:
        print(f"Flask sunucusu başlatılırken hata oluştu: {e}")
