import os
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import date
from supabase import create_client

# --- Supabase setup ---
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://tgirhkngkacpbvwpzbrq.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_h0098vYPRToMsw3zxdRK7A_5aIHl9ZZ')
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-HK,zh;q=0.9,en;q=0.8',
}
TODAY = str(date.today())


def parse_price(text):
    if not text:
        return None, None, text
    text = text.strip()
    nums = re.findall(r'[\d,]+\.?\d*', text.replace(',', ''))
    nums = [float(n) for n in nums if float(n) > 0]
    if len(nums) >= 2:
        return min(nums), max(nums), text
    elif len(nums) == 1:
        return nums[0], nums[0], text
    return None, None, text


def upsert_product(data):
    try:
        existing = supabase.table('products').select('id').eq('model', data['model']).eq('source', data['source']).execute()
        if existing.data:
            supabase.table('products').update({
                'price_min': data.get('price_min'),
                'price_max': data.get('price_max'),
                'price_display': data.get('price_display'),
                'image_url': data.get('image_url'),
                'updated_date': TODAY,
                'last_checked': 'now()'
            }).eq('id', existing.data[0]['id']).execute()
            print(f'Updated: {data["product_name"]} -> {data["price_display"]} | img: {data.get("image_url", "none")}')
        else:
            data['updated_date'] = TODAY
            supabase.table('products').insert(data).execute()
            print(f'Inserted: {data["product_name"]} -> {data["price_display"]} | img: {data.get("image_url", "none")}')
    except Exception as e:
        print(f'Error upserting {data.get("product_name")}: {e}')


# ======================
# 1. Healthtop
# ======================
def crawl_healthtop():
    print('\n=== Crawling Healthtop ===' )
    return  # TODO: Fix Healthtop URL structure - should be /products_en?page=N
    base_url = 'https://healthtop.com.hk'
    categories = [
        ('Wheelchairs-and-Walking-Aids', 'wheelchair'),
        ('Shower-Toilet-Accessories', 'toilet_aid'),
        ('Nursing-Bed', 'nursing_bed'),
        ('Transfer-Aids-Restraint-Products', 'transfer_aid'),
        ('Pressure-Relieving-Products', 'pressure_relief'),
    ]
    for cat_path, cat_key in categories:
        page = 1
        while True:
            url = f'{base_url}/{cat_path}?page={page}'
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code != 200:
                    break
                soup = BeautifulSoup(resp.text, 'html.parser')
                products = soup.select('.product-thumb')
                if not products:
                    break
                for prod in products:
                    try:
                        name_tag = prod.select_one('.name a')
                        price_tag = prod.select_one('.price')
                        img_tag = prod.select_one('img')
                        if not name_tag:
                            continue
                        name = name_tag.get_text(strip=True)
                        price_text = price_tag.get_text(strip=True) if price_tag else ''
                        pmin, pmax, pdisplay = parse_price(price_text)
                        product_url = base_url + name_tag.get('href', '')
                        # Extract model from URL
                        model = product_url.rstrip('/').split('/')[-1]
                        if not model or model == 'products_en':
                            model = name[:40]
                        # Image URL
                        img_url = ''
                        if img_tag:
                            src = img_tag.get('src') or img_tag.get('data-src') or ''
                            if src and not src.startswith('http'):
                                src = base_url + src
                            img_url = src
                        upsert_product({
                            'source': 'healthtop',
                            'source_name': 'Healthtop 唯健康',
                            'category': cat_key,
                            'product_name': name,
                            'model': model,
                            'price_min': pmin,
                            'price_max': pmax,
                            'price_display': pdisplay,
                            'image_url': img_url,
                            'url': product_url,
                            'phone': '2413 7867',
                            'specs': [],
                            'tags': [],
                            'notes': ''
                        })
                    except Exception as e:
                        print(f'  Product error: {e}')
                # Check if next page exists
                next_page = soup.select_one('.pagination .active + li a')
                if not next_page:
                    break
                page += 1
                time.sleep(1)
            except Exception as e:
                print(f'  Category error {url}: {e}')
                break


# ======================
# 2. Rehabexpress
# ======================
def crawl_rehabexpress():
    print('\n=== Crawling Rehabexpress ===' )
    base_url = 'https://www.rehabexpress.com.hk'
    categories = [
        ('mobility.html', 'wheelchair'),
        ('anatomical-support-and-decompression-supplies.html', 'pressure_relief'),
        ('assisted-daily-living-products.html', 'daily_aid'),
        ('fitness-and-rehab-products.html', 'rehab_equipment'),
    ]
    for cat_path, cat_key in categories:
        page = 1
        while True:
            url = f'{base_url}/{cat_path}?p={page}'
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code != 200:
                    break
                soup = BeautifulSoup(resp.text, 'html.parser')
                products = soup.select('.product-item-info')
                if not products:
                    break
                for prod in products:
                    try:
                        name_tag = prod.select_one('.product-item-link')
                        price_tag = prod.select_one('.price')
                        img_tag = prod.select_one('.product-image-photo')
                        if not name_tag:
                            continue
                        name = name_tag.get_text(strip=True)
                        price_text = price_tag.get_text(strip=True) if price_tag else ''
                        pmin, pmax, pdisplay = parse_price(price_text)
                        product_url = name_tag.get('href', '')
                        model = product_url.rstrip('/').split('/')[-1].split('.')[0]
                        if not model:
                            model = name[:40]
                        # Image URL
                        img_url = ''
                        if img_tag:
                            src = img_tag.get('src') or img_tag.get('data-src') or ''
                            img_url = src
                        upsert_product({
                            'source': 'rehabexpress',
                            'source_name': 'Rehabexpress 復康速遞',
                            'category': cat_key,
                            'product_name': name,
                            'model': f'RE-{model}',
                            'price_min': pmin,
                            'price_max': pmax,
                            'price_display': pdisplay,
                            'image_url': img_url,
                            'url': product_url,
                            'phone': '8206 6160',
                            'specs': [],
                            'tags': [],
                            'notes': ''
                        })
                    except Exception as e:
                        print(f'  Product error: {e}')
                # Pagination check
                next_btn = soup.select_one('a.action.next')
                if not next_btn:
                    break
                page += 1
                time.sleep(1)
            except Exception as e:
                print(f'  Category error {url}: {e}')
                break


# ======================
# 3. Easy66
# ======================
def crawl_easy66():
    print('\n=== Crawling Easy66 ===' )
    base_url = 'https://www.easy66.com.hk'
    categories = [
        ('categories/wheelchair', 'wheelchair'),
        ('categories/walkers', 'walking_aid'),
        ('categories/handrail', 'handrail'),
        ('categories/toilet-aids', 'toilet_aid'),
        ('categories/rollators', 'rollator'),
    ]
    for cat_path, cat_key in categories:
        page = 1
        while True:
            url = f'{base_url}/{cat_path}?page={page}'
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code == 404:
                    break
                if resp.status_code != 200:
                    break
                soup = BeautifulSoup(resp.text, 'html.parser')
                products = soup.select('.product-item, .product-card, article.product')
                if not products:
                    # Try alternate selectors
                    products = soup.select('[data-product-id]')
                if not products:
                    break
                found_any = False
                for prod in products:
                    try:
                        name_tag = prod.select_one('a.product-item__title, .product-name a, h2 a, h3 a, .title a')
                        if not name_tag:
                            name_tag = prod.select_one('a[href*="/products/"]')
                        price_tag = prod.select_one('.price, .product-price, .price-item')
                        img_tag = prod.select_one('img')
                        if not name_tag:
                            continue
                        found_any = True
                        name = name_tag.get_text(strip=True)
                        price_text = price_tag.get_text(strip=True) if price_tag else ''
                        pmin, pmax, pdisplay = parse_price(price_text)
                        href = name_tag.get('href', '')
                        if href and not href.startswith('http'):
                            href = base_url + href
                        model = href.rstrip('/').split('/')[-1]
                        if not model:
                            model = name[:40]
                        # Image URL
                        img_url = ''
                        if img_tag:
                            src = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-lazy-src') or ''
                            if src.startswith('//'):
                                src = 'https:' + src
                            elif src and not src.startswith('http'):
                                src = base_url + src
                            img_url = src
                        upsert_product({
                            'source': 'easy66',
                            'source_name': 'Easy66 樂齡網',
                            'category': cat_key,
                            'product_name': name,
                            'model': f'E66-{model}',
                            'price_min': pmin,
                            'price_max': pmax,
                            'price_display': pdisplay,
                            'image_url': img_url,
                            'url': href,
                            'phone': '3426 9090',
                            'specs': [],
                            'tags': [],
                            'notes': ''
                        })
                    except Exception as e:
                        print(f'  Product error: {e}')
                if not found_any:
                    break
                # Pagination: stop if no next page link
                next_btn = soup.select_one('a[rel="next"], .pagination__next, a.next')
                if not next_btn:
                    break
                page += 1
                time.sleep(1)
            except Exception as e:
                print(f'  Category error {url}: {e}')
                break


# ======================
# Main
# ======================
if __name__ == '__main__':
    print(f'Starting crawler - {TODAY}')
    crawl_healthtop()
    crawl_rehabexpress()
    crawl_easy66()
    print('\nDone!')
