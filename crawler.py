import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from datetime import date
from supabase import create_client

# --- Supabase setup ---
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://tgirhkngkacpbvwpzbrq.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_h0098vYPRToMsw3zxdRK7A_5aIHl9ZZ')
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
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
                'updated_date': TODAY,
                'last_checked': 'now()'
            }).eq('id', existing.data[0]['id']).execute()
            print(f'Updated: {data["product_name"]} -> {data["price_display"]}')
        else:
            data['updated_date'] = TODAY
            supabase.table('products').insert(data).execute()
            print(f'Inserted: {data["product_name"]} -> {data["price_display"]}')
    except Exception as e:
        print(f'Error upserting {data.get("product_name")}: {e}')

# =====================
# 1. Healthtop 唯健康
# =====================
def crawl_healthtop():
    print('\n=== Crawling Healthtop 唯健康 ===')
    categories = [
        'https://www.healthtop.com.hk/wheelchair',
        'https://www.healthtop.com.hk/shower-commode-chair',
        'https://www.healthtop.com.hk/toilet-safety',
        'https://www.healthtop.com.hk/grab-bar-handrail',
        'https://www.healthtop.com.hk/bed-rail',
        'https://www.healthtop.com.hk/ramp',
        'https://www.healthtop.com.hk/bath-board',
        'https://www.healthtop.com.hk/air-mattress',
        'https://www.healthtop.com.hk/reacher',
    ]
    cat_map = {
        'wheelchair': 'wheelchair', 'shower-commode': 'shower',
        'toilet': 'toilet', 'grab-bar': 'handrail', 'handrail': 'handrail',
        'bed-rail': 'bedrail', 'ramp': 'ramp', 'bath-board': 'bathboard',
        'air-mattress': 'mattress', 'reacher': 'reacher'
    }
    for url in categories:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            products = soup.select('.product-thumb, .product-layout')
            cat_key = 'other'
            for k, v in cat_map.items():
                if k in url:
                    cat_key = v
                    break
            for p in products:
                try:
                    name_el = p.select_one('.caption h4 a, .name a')
                    price_el = p.select_one('.price-new, .price')
                    link_el = p.select_one('a[href]')
                    if not name_el:
                        continue
                    name = name_el.text.strip()
                    price_text = price_el.text.strip() if price_el else '請查詢'
                    product_url = link_el['href'] if link_el else url
                    model = product_url.split('/')[-1].split('?')[0] or name[:20]
                    pmin, pmax, pdisplay = parse_price(price_text)
                    upsert_product({
                        'source': 'healthtop',
                        'source_name': '唯健康',
                        'category': cat_key,
                        'product_name': name,
                        'model': model,
                        'price_min': pmin,
                        'price_max': pmax,
                        'price_display': pdisplay,
                        'phone': '2413 7867',
                        'url': product_url,
                        'specs': [],
                        'tags': [],
                        'notes': ''
                    })
                except Exception as e:
                    print(f'  Product error: {e}')
            time.sleep(1)
        except Exception as e:
            print(f'  Category error {url}: {e}')

# =====================
# 2. Rehabexpress 復康速遞
# =====================
def crawl_rehabexpress():
    print('\n=== Crawling Rehabexpress 復康速遞 ===')
    categories = [
        ('https://www.rehabexpress.com.hk/product-category/wheelchair/', 'wheelchair'),
        ('https://www.rehabexpress.com.hk/product-category/shower-chair/', 'shower'),
        ('https://www.rehabexpress.com.hk/product-category/toilet-aid/', 'toilet'),
        ('https://www.rehabexpress.com.hk/product-category/handrail/', 'handrail'),
        ('https://www.rehabexpress.com.hk/product-category/bed-rail/', 'bedrail'),
        ('https://www.rehabexpress.com.hk/product-category/ramp/', 'ramp'),
        ('https://www.rehabexpress.com.hk/product-category/bath-board/', 'bathboard'),
        ('https://www.rehabexpress.com.hk/product-category/air-mattress/', 'mattress'),
    ]
    for url, cat_key in categories:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            products = soup.select('li.product, .product-item')
            for p in products:
                try:
                    name_el = p.select_one('h2.woocommerce-loop-product__title, .product-title')
                    price_el = p.select_one('.price .amount, .woocommerce-Price-amount')
                    link_el = p.select_one('a.woocommerce-LoopProduct-link, a[href]')
                    if not name_el:
                        continue
                    name = name_el.text.strip()
                    price_text = price_el.text.strip() if price_el else '請查詢'
                    product_url = link_el['href'] if link_el else url
                    model = product_url.rstrip('/').split('/')[-1] or name[:20]
                    pmin, pmax, pdisplay = parse_price(price_text)
                    upsert_product({
                        'source': 'rehabexpress',
                        'source_name': '復康速遞',
                        'category': cat_key,
                        'product_name': name,
                        'model': model,
                        'price_min': pmin,
                        'price_max': pmax,
                        'price_display': pdisplay,
                        'phone': '2396 0570',
                        'url': product_url,
                        'specs': [],
                        'tags': [],
                        'notes': ''
                    })
                except Exception as e:
                    print(f'  Product error: {e}')
            time.sleep(1)
        except Exception as e:
            print(f'  Category error {url}: {e}')

# =====================
# 3. EASY66
# =====================
def crawl_easy66():
    print('\n=== Crawling EASY66 ===')
    categories = [
        ('https://www.easy66.com.hk/category/wheelchair', 'wheelchair'),
        ('https://www.easy66.com.hk/category/shower-chair', 'shower'),
        ('https://www.easy66.com.hk/category/toilet-aid', 'toilet'),
        ('https://www.easy66.com.hk/category/handrail', 'handrail'),
        ('https://www.easy66.com.hk/category/bed-rail', 'bedrail'),
        ('https://www.easy66.com.hk/category/ramp', 'ramp'),
        ('https://www.easy66.com.hk/category/bath-board', 'bathboard'),
        ('https://www.easy66.com.hk/category/mattress', 'mattress'),
    ]
    for url, cat_key in categories:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            products = soup.select('.product-item, .item-product, article.product')
            for p in products:
                try:
                    name_el = p.select_one('h2, h3, .product-name, .title')
                    price_el = p.select_one('.price, .product-price, span[class*=price]')
                    link_el = p.select_one('a[href]')
                    if not name_el:
                        continue
                    name = name_el.text.strip()
                    price_text = price_el.text.strip() if price_el else '請查詢'
                    product_url = link_el['href'] if link_el else url
                    model = product_url.rstrip('/').split('/')[-1] or name[:20]
                    pmin, pmax, pdisplay = parse_price(price_text)
                    upsert_product({
                        'source': 'easy66',
                        'source_name': 'EASY66',
                        'category': cat_key,
                        'product_name': name,
                        'model': model,
                        'price_min': pmin,
                        'price_max': pmax,
                        'price_display': pdisplay,
                        'phone': '3426 9090',
                        'url': product_url,
                        'specs': [],
                        'tags': [],
                        'notes': ''
                    })
                except Exception as e:
                    print(f'  Product error: {e}')
            time.sleep(1)
        except Exception as e:
            print(f'  Category error {url}: {e}')

# =====================
# Main
# =====================
if __name__ == '__main__':
    print(f'Starting crawler - {TODAY}')
    crawl_healthtop()
    crawl_rehabexpress()
    crawl_easy66()
    print('\nDone!')
