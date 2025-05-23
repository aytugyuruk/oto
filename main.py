import os
import shutil  # Klasör silmek için
import yt_dlp
from supabase import create_client, Client
from dotenv import load_dotenv

# --- Yapılandırma ---
# .env dosyasından ortam değişkenlerini yükle
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
# Örnek: "https://www.youtube.com/@username" veya "https://www.youtube.com/channel/UCXXXXXXX"
CHANNEL_URL = os.getenv("CHANNEL_URL")

# İndirme ve Supabase ayarları
DOWNLOAD_DIR = "ses_indirmeleri"  # İndirilen ses dosyalarının kaydedileceği klasör
BUCKET_NAME = "audio"  # Supabase Storage bucket adınız (orijinaldeki gibi)

# --- Supabase İstemcisini Başlatma ---
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("Supabase bağlantısı başarılı!")
except Exception as e:
    print(f"Supabase bağlantısı sırasında bir hata oluştu: {e}")
    exit(1) # Hata durumunda programdan çık

# --- Ana Fonksiyonlar ---

def get_latest_video_info(channel_url: str) -> dict | None:
    """Bir YouTube kanalındaki en son videonun bilgilerini alır."""
    ydl_opts = {
        'extract_flat': True,       # Tüm videolar için tam bilgi almadan listele
        'playlistend': 1,           # Sadece listedeki ilk videoyu (en sonuncuyu) işle
        'quiet': True,              # yt-dlp'nin normal çıktılarını gizle
        'no_warnings': True,        # Uyarıları gizle
        'ignoreerrors': True,       # Hataları yoksay ve devam etmeye çalış
    }
    print(f"'{channel_url}' kanalından en son video bilgileri alınıyor...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            channel_info = ydl.extract_info(channel_url, download=False)
            if channel_info and 'entries' in channel_info and channel_info['entries']:
                latest_video = channel_info['entries'][0]
                video_title = latest_video.get('title', 'Bilinmeyen Başlık')
                # extract_flat bazen tam URL yerine sadece ID verir
                video_id = latest_video.get('id')
                video_url = latest_video.get('url')
                if not video_url or not video_url.startswith('http'):
                    video_url = f"https://www.youtube.com/watch?v={video_id}"

                print(f"En son video bulundu: '{video_title}' ({video_url})")
                return {'title': video_title, 'url': video_url, 'id': video_id}
            else:
                print("Kanaldan video bilgisi alınamadı veya kanal boş.")
                return None
    except Exception as e:
        print(f"Video bilgileri alınırken hata: {e}")
        return None

def download_video_audio(video_url: str, video_title: str) -> str | None:
    """Bir videonun sesini MP3 olarak indirir."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True) # İndirme klasörünü oluştur (varsa dokunma)

    # Dosya adı için video başlığını güvenli hale getir
    safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in video_title).rstrip()
    # Aynı isimde dosya varsa üzerine yazılmaması için ID eklenebilir veya benzersiz bir isim üretilebilir.
    # Şimdilik basit tutuyoruz, yt-dlp'nin üreteceği isme güveniyoruz (genellikle başlık içerir).
    # yt-dlp'ye çıktı şablonunu vererek dosya adını daha iyi kontrol edebiliriz.
    output_template = os.path.join(DOWNLOAD_DIR, f"{safe_title}.%(ext)s")

    ydl_opts = {
        'format': 'bestaudio/best',  # En iyi kalitede sesi seç
        'outtmpl': output_template,   # İndirilecek dosyanın adı ve yolu için şablon
        'postprocessors': [{
            'key': 'FFmpegExtractAudio', # Sesi ayıkla
            'preferredcodec': 'mp3',     # MP3 formatına dönüştür
            'preferredquality': '192',   # MP3 kalitesi (örneğin 192 Kbps)
        }],
        'quiet': False,             # İndirme sırasında ilerlemeyi göster
        'no_warnings': False,
        'retries': 3,               # İndirme başarısız olursa 3 kez tekrar dene
    }
    print(f"'{video_title}' videosunun sesi indiriliyor...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            error_code = ydl.download([video_url])
            if error_code != 0:
                print(f"Ses indirilirken bir sorun oluştu (yt-dlp hata kodu: {error_code}).")
                return None

        # İndirilen MP3 dosyasını bul (FFmpeg sonrası adı değişebilir)
        for f in os.listdir(DOWNLOAD_DIR):
            # Dosya adının video başlığıyla başladığını ve .mp3 ile bittiğini kontrol et
            if f.startswith(safe_title) and f.endswith(".mp3"):
                downloaded_file_path = os.path.join(DOWNLOAD_DIR, f)
                print(f"Ses dosyası başarıyla indirildi: {downloaded_file_path}")
                return downloaded_file_path
        
        print("İndirilen MP3 dosyası bulunamadı. Çıktı şablonu veya dosya adı kontrol edilmeli.")
        return None

    except Exception as e:
        print(f"Ses indirilirken hata: {e}")
        return None

def upload_audio_to_supabase(file_path: str, bucket_name: str) -> bool:
    """Bir ses dosyasını Supabase Storage'a yükler."""
    if not file_path or not os.path.exists(file_path):
        print(f"Yüklenecek dosya bulunamadı: {file_path}")
        return False

    file_name = os.path.basename(file_path)
    print(f"'{file_name}' dosyası Supabase Storage'daki '{bucket_name}' bucket'ına yükleniyor...")
    try:
        with open(file_path, "rb") as f:
            # Supabase'e yükleme (varsa üzerine yazar - upsert: "true")
            response = supabase.storage.from_(bucket_name).upload(
                path=file_name,
                file=f,
                file_options={"content-type": "audio/mpeg", "upsert": "true"}
            )
        print(f"'{file_name}' başarıyla yüklendi.")
        return True
    except Exception as e:
        print(f"Supabase'e yüklenirken hata: {e}")
        if hasattr(e, 'details'): print(f"Detaylar: {e.details}")
        if hasattr(e, 'message'): print(f"Mesaj: {e.message}")
        return False

def cleanup_downloads():
    """İndirme klasörünü ve içindekileri temizler."""
    if os.path.exists(DOWNLOAD_DIR):
        try:
            shutil.rmtree(DOWNLOAD_DIR)
            print(f"'{DOWNLOAD_DIR}' klasörü başarıyla temizlendi.")
        except Exception as e:
            print(f"İndirme klasörü temizlenirken hata oluştu: {e}")

# --- Betiğin Ana Çalışma Bloğu ---
if __name__ == "__main__":
    # Gerekli ortam değişkenlerinin ayarlandığından emin ol
    if not all([SUPABASE_URL, SUPABASE_KEY, CHANNEL_URL]):
        print("Hata: SUPABASE_URL, SUPABASE_KEY, ve CHANNEL_URL ortam değişkenlerinden biri veya birkaçı ayarlanmamış.")
        print("Lütfen .env dosyanızı kontrol edin veya ortam değişkenlerini ayarlayın.")
        exit(1)

    print("İşlem başlatılıyor...")
    video_info = get_latest_video_info(CHANNEL_URL)

    if video_info:
        audio_file_path = download_video_audio(video_info['url'], video_info['title'])
        
        if audio_file_path:
            success = upload_audio_to_supabase(audio_file_path, BUCKET_NAME)
            if success:
                print("👍 İşlem başarıyla tamamlandı!")
            else:
                print("👎 Yükleme başarısız oldu.")
        else:
            print("Ses indirme işlemi başarısız oldu.")
    else:
        print("En son video bilgileri alınamadı. İşlem durduruldu.")
    
    # İndirilen dosyaları temizle
    cleanup_downloads()
    print("İşlem sonlandı.")
