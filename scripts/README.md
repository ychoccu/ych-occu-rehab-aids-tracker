# YCH Rehab Aids Tracker — GitHub Actions 自動價格更新

## 概覽 Overview

依個 GitHub Actions workflow 係 Perplexity AI cron 嘅備份 (backup)。
每逢**星期六早上 9am（香港時間）**自動執行，用 Google Gemini AI 抓取各供應商網站嘅最新價格，更新 `products.json` 同埋重建獨立 HTML 檔案。

> **注意：** 依個 workflow 同 Perplexity cron 並行運行。Perplexity 喺**星期日 9am** 跑，呢個喺**星期六 9am** 跑。

---

## Setup（部門同事一次性設定）

### Step 1: 申請免費 Google Gemini API Key
1. 用部門 Gmail (ychoccupational@gmail.com) 去 https://aistudio.google.com/apikey
2. 撳 "Create API Key" → 選 "Create API key in new project"
3. Copy 出嚟個 key（樣子似 `AIzaSy...`）
4. **唔好 commit 入 Git！** 只係下一步用嚟設定 GitHub Secret

### Step 2: 設定 GitHub Secret
1. 去 https://github.com/ychoccu/ych-occu-rehab-aids-tracker/settings/secrets/actions
2. 撳 "New repository secret"
3. Name: `GEMINI_API_KEY`
4. Secret: paste 剛才嗰個 key
5. 撳 "Add secret"

### Step 3: 測試手動 trigger
1. 去 Actions tab → "Weekly Price Check" workflow
2. 撳 "Run workflow" → 揀 main branch → Run
3. 等 2-3 分鐘睇 log，確認所有產品都 process 到

### Step 4: 確認 schedule
Workflow 已 set 做星期六 9am HKT 自動跑。

---

## Safety Features

1. **Sanity check**: 新價同舊價如果差超過 3 倍（or 少過 1/3），自動 skip 唔 update。Log 入 "SUSPICIOUS" list 等人工 review。
2. **Tier 2 protection**: Range-priced 產品（廁所加高器、扶手）只更新 price_min，永遠唔 touch price_display。
3. **Count assertion**: 任何時候 products 數目少咗，workflow fail。
4. **Skip on failure**: 任何單一產品 fetch / parse fail，只 skip 嗰一個，其他繼續行。
5. **Rate limiting**: 每個產品之間 sleep 5 秒，確保唔超過 Gemini free tier 15 RPM limit。

## Free Tier Budget

- Gemini 2.5 Flash free tier: **15 RPM, 1,500 requests/day**
- 我哋每星期跑 ~57 requests = ~3.8% of daily limit
- 完全夠用，唔需要 paid tier

---

## 運行時間表 Schedule

| Workflow | 時間 | 觸發方式 |
|---|---|---|
| 呢個 (GitHub Actions) | 星期六 9am HKT | `cron: "0 1 * * 6"` |
| Perplexity cron | 星期日 9am HKT | Perplexity 平台 |

---

## 手動觸發 Manual Trigger

1. 入去 GitHub repo 頁面
2. 撳 **Actions** 頁籤
3. 喺左邊 workflow 列表揀 **Weekly Price Check**
4. 撳 **Run workflow** 掣
5. (可選) 揀 `dry_run = true` → 只係 log 改動，唔會 commit

---

## 睇 Log / Debug 失敗

1. 入去 **Actions → Weekly Price Check → 最近一次 run**
2. 展開 `Run price checker` 步驟
3. 搵 `FAIL`、`WARN`、`SUSPICIOUS` 關鍵字：
   ```
   grep "FAIL\|WARN\|ERROR\|SUSPICIOUS" < 全部 log
   ```
4. 格式例子：
   ```
   FETCH FAIL [sc9]: HTTPSConnectionPool ... timed out
   SUSPICIOUS [cm3]: 2680 -> 26800 (ratio 10.00x), SKIPPING
   SKIP [cm5]: no valid price (raw=None)   ← HKTVmall (JS-rendered, expected)
   ```

---

## Tier 2 產品 (range-priced) 特別注意

以下產品係「價格範圍」：只自動更新 `price_min`（最低錨位），`price_max` 同 `price_display` **唔會自動改**，需要人手 review：

```
tr1, tr2, tr3, tr4, tr5   ← 廁椅/沐浴椅加配件
hr1, hr2, hr3, hr4, hr5, hr6  ← 扶手欄
```

每次有 Tier 2 價格改動，Summary 會打印 `*** manual review needed ***`。

---

## 安全規則 Safety Rules

- **絕對唔會刪除任何產品**（有 `assert len(data) == original_count` 保護）
- 只修改以下欄位：`price_min`, `price_max`, `price_display`, `last_checked`, `updated_date`
- Tier 2：只改 `price_min`，唔碰 `price_max` / `price_display`
- 如果 safety check 失敗：唔寫檔案，workflow 失敗報錯
- SUSPICIOUS 價格（變動超過 3x）：自動 skip，連 `last_checked` 都唔改

---

## 檔案結構 File Structure

```
.github/workflows/
  weekly-price-check.yml   ← GitHub Actions 定義

scripts/
  price_checker.py         ← 主入口，抓取 + 更新 products.json
  rebuild_html.py          ← 重建 standalone HTML（embed base64 圖片）
  requirements.txt         ← Python dependencies
  README.md                ← 本文件

  parsers/
    __init__.py            ← 統一 Gemini parser 入口
    gemini_extract.py      ← Gemini API price extractor（所有域名共用）
```

---

## 測試單個產品（本地）

```bash
# 設定 API key
export GEMINI_API_KEY="AIzaSy..."

# 先下載一個產品頁面到 HTML 檔案
curl -A "Mozilla/5.0" "https://www.justmed.com.hk/product/XXX/" -o /tmp/test.html

# 直接測試 Gemini extractor
python3 -c "
from scripts.parsers.gemini_extract import extract_price
html = open('/tmp/test.html').read()
print('Tier1 price:', extract_price(html, 'https://www.justmed.com.hk/product/XXX/', tier=1))
print('Tier2 min:  ', extract_price(html, 'https://www.justmed.com.hk/product/XXX/', tier=2))
"
```

---

## HKTVmall 注意事項

`cm5`（坐廁椅）同 `mat3`（床褥）係 HKTVmall 產品。HKTVmall 係 JavaScript 渲染嘅 SPA，靜態 HTML 抓取唔到價格。呢兩個產品喺每次 run 都會顯示為 **skipped**，需要人手更新。

---

*Last updated: 2026-06*
