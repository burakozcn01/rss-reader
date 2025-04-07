import requests
import json
from datetime import datetime
import sys

# API anahtarı
API_KEY = "OsTr/zP8i3cJGZMv1yIjSwQkIzcEjFp285X1qmj4mzs="

API_BASE_URL = "http://localhost:5000/api"

HEADERS = {
    "X-API-Key": API_KEY
}

def get_categories():
    """Tüm kategorileri çeker"""
    try:
        response = requests.get(f"{API_BASE_URL}/categories", headers=HEADERS)
        response.raise_for_status()  
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Kategoriler alınırken hata oluştu: {e}")
        sys.exit(1)

def get_category_entries(category_id, page=1, per_page=20):
    """Belirli bir kategorideki yazıları çeker"""
    try:
        response = requests.get(
            f"{API_BASE_URL}/categories/{category_id}/entries",
            headers=HEADERS,
            params={"page": page, "per_page": per_page}
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Yazılar alınırken hata oluştu: {e}")
        return None

def format_date(date_str):
    """ISO formatındaki tarihi daha okunabilir formata çevirir"""
    try:
        date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return date_obj.strftime("%d-%m-%Y %H:%M")
    except:
        return date_str

def display_categories(categories):
    """Kategorileri listeler"""
    print("\n=== KATEGORİLER ===")
    print("ID  | Feed # | İsim")
    print("----|--------|------------------")
    for category in categories:
        print(f"{category['id']:<4}| {category.get('feed_count', 0):<7}| {category['title']}")

def display_entries(entries_data):
    """Yazıları listeler"""
    if not entries_data or 'entries' not in entries_data or not entries_data['entries']:
        print("\nBu kategoride yazı bulunamadı.")
        return
    
    entries = entries_data['entries']
    pagination = entries_data.get('pagination', {})
    category = entries_data.get('category', {})
    
    print(f"\n=== {category.get('title', 'Kategori')} KATEGORİSİNDEKİ YAZILAR ===")
    print(f"Sayfa {pagination.get('page', 1)}/{pagination.get('pages', 1)} - Toplam {pagination.get('total', len(entries))} yazı")
    print()
    
    for i, entry in enumerate(entries, 1):
        published = format_date(entry.get('published_at', ''))
        feed_title = entry.get('feed', {}).get('title', 'Bilinmeyen Feed')
        
        print(f"{i}. {entry['title']}")
        print(f"   Feed: {feed_title} | Tarih: {published}")
        print(f"   URL: {entry['url']}")
        print()

def main():
    """Ana fonksiyon"""
    print("RSS Feed Kategori Okuyucu")
    print("-------------------------")
    
    categories = get_categories()
    if not categories:
        print("Hiç kategori bulunamadı.")
        return
    
    display_categories(categories)
    
    while True:
        try:
            category_id = input("\nListelemek istediğiniz kategori ID'sini girin (çıkış için q): ")
            
            if category_id.lower() == 'q':
                print("Program sonlandırılıyor...")
                break
            
            category_id = int(category_id)
            
            category_exists = any(cat['id'] == category_id for cat in categories)
            if not category_exists:
                print("Geçersiz kategori ID. Lütfen listeden bir ID seçin.")
                continue
            
            entries_data = get_category_entries(category_id)
            display_entries(entries_data)
            
            total_pages = entries_data.get('pagination', {}).get('pages', 1)
            current_page = 1
            
            while total_pages > 1:
                action = input(f"\nSayfa {current_page}/{total_pages} - [N]ext, [P]revious, [B]ack to categories, [Q]uit: ").lower()
                
                if action == 'n' and current_page < total_pages:
                    current_page += 1
                    entries_data = get_category_entries(category_id, page=current_page)
                    display_entries(entries_data)
                elif action == 'p' and current_page > 1:
                    current_page -= 1
                    entries_data = get_category_entries(category_id, page=current_page)
                    display_entries(entries_data)
                elif action == 'b':
                    break
                elif action == 'q':
                    print("Program sonlandırılıyor...")
                    return
                else:
                    print("Geçersiz seçim.")
            
        except ValueError:
            print("Lütfen geçerli bir sayı girin.")
        except KeyboardInterrupt:
            print("\nProgram sonlandırılıyor...")
            break

if __name__ == "__main__":
    main()