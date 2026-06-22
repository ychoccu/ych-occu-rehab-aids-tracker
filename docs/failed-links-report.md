# 失效連結 / 攞唔到價 報告

**最後更新：** 2026-06-22（Run #6 之後）
**Run 編號：** Weekly Price Check #6
**總共失敗：** 23 / 35 件產品

呢份報告係 Weekly Price Check 自動攞唔到價嘅產品清單。失敗分 3 類：
1. **🔴 連結失效** — 個 URL 404 / SSL error，無法 fetch
2. **🟡 網頁無價** — 網頁存在但本身就冇列價（產品 note 已標明「請致電查詢」），系統其實永遠攞唔到
3. **🟠 AI 攞錯價** — 網頁有價但 AI 喺一堆 sidebar/「最近瀏覽」噪音入面揀錯（`d11c203` commit 已改善，待 sync）

---

## 🔴 第 1 類：連結失效（3 件，必須換 URL）

呢 3 件係**最緊急**，因為連網頁都打唔開，需要重新搜尋新網址。

| ID | 產品名稱 | Model | 供應商 | 電話 | 舊 URL | 錯誤 | 上次價 |
|---|---|---|---|---|---|---|---|
| **w5** | 手推式摺背型輪椅 | H508 | 信義醫療 | 3904 9019 | [justicemed.com/product.php?sid=20&id=671](https://www.justicemed.com/product.php?sid=20&id=671) | **SSL CERTIFICATE_VERIFY_FAILED** — 網站 SSL 證書壞咗 | HK$1,880 |
| **r3** | 摺疊式輪椅斜板 | WA200 | 卓越 Supreme | 3690 1468 | [supreme.com.hk](https://www.supreme.com.hk/) | **404 Not Found** — 連主頁都打唔開（注意：呢個係 `supreme.com.hk`，唔係實際嘅 `suprememed.com.hk`） | HK$1,500–$2,800 |
| **bed2** | 電動三功能護理床 (TopOne, 2.5呎/3呎) | FHA-FO-KS-828A/888B | 唯健康 Health Top | 2413 7867 | [healthtop.com.hk/FHA-FO-KS-828A...](https://healthtop.com.hk/FHA-FO-KS-828ATOPONE%E4%B8%89%E5%8A%9F%E8%83%BD%E9%9B%BB%E5%8B%95%E8%AD%B7%E7%90%86%E5%BA%8A) | **404 Not Found** — healthtop 改咗條 product link | HK$13,600 |

### 建議跟進
- **w5**：打 WhatsApp 54062554 問下信義有冇新 URL；或者用 `suprememed.com.hk` 嘅同類產品做替代。
- **r3**：產品 URL 應該係 `suprememed.com.hk`，唔係 `supreme.com.hk`。**呢個係 typo**，要喺 products.json 改返。
- **bed2**：去 [healthtop.com.hk](https://healthtop.com.hk) 搵返「電動三功能護理床 TopOne」嘅新 product page。

---

## 🟡 第 2 類：網頁本身冇列價（11 件，建議標 `manual_only`）

呢啲產品個網頁可以開到，但**個價要打電話問**。系統每次都會試，每次都會失敗，浪費 API quota。建議將呢類產品標記做 `manual_only: true`，跳過自動 check。

### 唯健康 Health Top（5 件）
> 整個 healthtop.com.hk 網站好多產品都係**唔列價**嘅，要全部打 2413 7867 查詢。

| ID | 產品 | Model | URL | Note |
|---|---|---|---|---|
| **w6** | 功能型鋁合金小輪手動輪椅 | FHW-13 | [link](https://healthtop.com.hk/%E5%8A%9F%E8%83%BD%E5%9E%8B%E9%8B%81%E5%90%88%E9%87%91%E5%B0%8F%E8%BC%AA%E6%89%8B%E5%8B%95%E8%BC%AA%E6%A4%85-FHW-13) | 網頁未列價 |
| **sc1** | 洗澡椅（扶手可拆） | FHA-DW-3500 | [link](https://healthtop.com.hk/浴室用具/沐浴椅?product_id=444) | 「網頁未列價, 請致電查詢」 |
| **tr1** | 廁所加高器 (3"/4"/5.5") | FHA-TB-9000 | [link](https://healthtop.com.hk/浴室用具/廁所加高器/廁所加高器FHA-TB-9000) | 「網頁未列價, 請致電查詢」 |
| **rc3** | (新型) 磁性取物器 | FHA-HE-1626 | [link](https://healthtop.com.hk/取物器FHA-HE-1626) | 「原 QR 已失效, 唯健康 online product page 未找到, 請致電」|
| **rmp1** | 橡膠門檻斜板 (多尺寸) | FHA-WS-RUB | [link](https://healthtop.com.hk/index.php?route=product/product&product_id=423) | 參考價 $370-$650, 視乎尺寸 |

### 卓越 Supreme（3 件）
> 整個 suprememed.com.hk 都係**網上不接受付款，價錢以電話查詢為準**。

| ID | 產品 | Model | URL | Note |
|---|---|---|---|---|
| **cm2** | 摺合式沐浴便椅 | CA1360 | [link](https://www.suprememed.com.hk/tc/products_detail.php?c1id=8&id=425) | 「網上不接受付款，價錢以電話查詢為準」 |
| **cm4** | 四輪沐浴便椅 V-Chair | CS880A | [link](https://www.suprememed.com.hk/tc/products_detail.php?c1id=8&id=666) | 個 price_display 都係「請致電查詢」 |
| **tr4** | 座廁加高墊 - 有蓋 (3"/4"/5") | CX900C | [link](https://www.suprememed.com.hk/tc/products_detail.php?c1id=8&id=524) | 「網上不接受付款」 |

### 康健醫療 Medicare（3 件）
> 部分 medicare.com.hk 產品頁係多型號嘅 listing page，唔列具體價。

| ID | 產品 | Model | URL |
|---|---|---|---|
| **cm1** | 固定型坐廁椅 | ECM00407 | [link](https://www.medicare.com.hk/zh-hant/care/113/) |
| **cm6** | 304不銹鋼沐浴便椅（可選 Tilt-bar）| ECM30442 / ECM30444S | [link](https://www.medicare.com.hk/zh-hant/care/94/) |
| **hr5** | 1.25" 304不銹鋼防滑扶手 | EMS00502 | [link](https://www.medicare.com.hk/zh-hant/care/186/) |

### 建議跟進
1. 由我（或之後 Sam）加 `manual_only: true` 落呢 11 件產品。
2. 系統見到呢個 flag 就**跳過 LLM call**，直接標 `last_checked = 今日`、`last_check_status = "manual_only"`。
3. patient view 個 UI 喺呢類產品旁邊細細粒字寫「**請致電查詢最新價**」。

---

## 🟠 第 3 類：AI 攞錯價（9 件，已有改善方案）

呢啲產品個網頁**有列價**，但 AI 喺 sidebar / 「最近瀏覽」 / 相關產品 推介嘅噪音入面揀錯。

| ID | 產品 | Model | 供應商 | URL | 上次價 |
|---|---|---|---|---|---|
| **w9** | 可躺式高背輪椅 | GHM-WC-RC | 家得康 | [link](https://www.gethealth.com.hk/%E5%95%86%E5%93%81/%E5%8F%AF%E8%BA%BA%E5%BC%8F%E9%AB%98%E8%83%8C%E8%BC%AA%E6%A4%85-%E5%A4%9A%E5%8A%9F%E8%83%BD%E8%A8%AD%E8%A8%88-%E6%A4%85%E8%83%8C%E5%8F%AF%E5%BE%8C%E5%82%BE/) | HK$3,900 |
| **sc3** | 鋁合金扶手旋轉沐浴椅 (360°) | GHM-SC-RT360 | 家得康 | [link](https://www.gethealth.com.hk/商品/鋁合金扶手旋轉沐浴椅-360o旋轉-扶手可翻/) | HK$750 |
| **sc4** | 鋁合金軟墊沐浴椅 (輕巧迷你) | GHM-SC-FZ03 | 家得康 | [link](https://www.gethealth.com.hk/商品/鋁合金軟墊沐浴椅-輕巧迷你/) | HK$450 |
| **cm5** | 不銹鋼沐浴便椅 (總闊 18.3") | GHM-SC-CM04-PU | 家得康 | [link](https://www.gethealth.com.hk/商品/不銹鋼沐浴便椅-總闊僅18-3吋/) | HK$1,700 |
| **bed1** | 三功能電動護理床（經濟之選）| GHM-NB-888 (B/C) | 家得康 | [link](https://www.gethealth.com.hk/%E5%95%86%E5%93%81/%e4%b8%89%e5%8a%9f%e8%83%bd%e9%9b%bb%e5%8b%95%e8%ad%b7%e7%90%86%e5%ba%8a-%e7%b6%93%e6%bf%9f%e4%b9%8b%e9%81%b8-%e5%8f%af%e9%81%b83%e5%91%8e2-5%e5%91%8e/) | HK$7,450 |
| **mat3** | Effect 減壓氣墊床（台灣品牌）| GHM-PM-EFFECT | 家得康 | [link](https://www.gethealth.com.hk/商品/effect-減壓氣墊床-台灣品牌/) | HK$1,850 |
| **hr1** | 防滑浴室扶手 | NOT-F19467 | 真善美 | [link](https://www.justmed.com.hk/product-detail.php?id=80) | HK$190–$250 |
| **hr3** | DBPE 安全防滑扶手 | DBPE-0001 | 盈康 | [link](https://www.healthyliving.com.hk/product-category/%E6%B5%B4%E5%AE%A4%E5%AE%89%E5%85%A8/%E6%B5%B4%E5%AE%A4%E6%89%B6%E6%89%8B-%E6%B5%B4%E5%AE%A4%E5%AE%89%E5%85%A8/) | HK$200–$350 |
| **hr6** | DBPE 上翻式浴室扶手 | DBPE-0014 | 盈康 | [link](https://www.healthyliving.com.hk/product-category/%E6%B5%B4%E5%AE%A4%E5%AE%89%E5%85%A8/%E6%B5%B4%E5%AE%A4%E6%89%B6%E6%89%8B-%E6%B5%B4%E5%AE%A4%E5%AE%89%E5%85%A8/) | HK$880 / $1,080 |

### 改善方案（已寫，未 deploy）
- Commit `d11c203` 已經喺 debug repo：俾產品 name + model 做 hint 俾 AI，等佢識揀返自己嗰個。
- **下一步**：去 [Sync fork](https://github.com/ychoccu/ych-occu-rehab-aids-tracker/actions/workflows/sync-fork.yml) 撳 Run → 再 run 一次 weekly-price-check（dry_run=true）→ 預期呢 9 個會有 6-8 個恢復成功。
- 注意：hr3 / hr6 個 URL 係 **category 頁**，唔係單一產品頁，可能要重新搵每個 model 嘅獨立 product page。

---

## 📊 統計

| 類別 | 數量 | 跟進 |
|---|---|---|
| 🔴 連結失效 | 3 | 人手搵新 URL |
| 🟡 網頁無價（請致電） | 11 | 加 `manual_only: true` |
| 🟠 AI 攞錯價 | 9 | Sync `d11c203` deploy 改善 |
| ✅ 成功 | 12 | — |
| **總計** | **35** | |

---

## 📞 供應商電話 quick reference

| 供應商 | 電話 | WhatsApp / 備註 |
|---|---|---|
| 唯健康 Health Top | 2413 7867 | 好多產品要打電話問 |
| 家得康 GetHealth | 2432 2028 | 網頁有價，AI 攞錯而已 |
| 卓越醫療 Supreme | 3690 1468 | 全部要打電話 |
| 康健醫療 Medicare | 2687 6380 | 部分 listing page 冇具體價 |
| 真善美 JustMed | 2742 4370 | — |
| 盈康 Healthy Living | 3426 9090 | — |
| 信義醫療 JusticeMed | 3904 9019 | WhatsApp 54062554 |

---

*呢份報告由 Run #6 (2026-06-22 11:01 UTC) 嘅 log 整理而成。下次 weekly check 之後可以重新更新呢份 report。*
