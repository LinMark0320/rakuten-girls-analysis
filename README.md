# 樂天女孩卡二級市場行情與賣家操盤寶典 📊

> 專為卡舖賣家與重度收藏家打造的樂天女孩（Rakuten Girls）收藏卡二級市場行情監控與檢索系統。

---

## 🌟 專案亮點

1. **官方 27 位主要在籍成員完整名單**：嚴格排除幹部與非跳舞行政，聚焦核心常規隊員（含高佳彬、河智媛、廉世彬、禹洙漢、金佳垠等韓援，以及孟潔、岱縈、若潼等本土門面）。
2. **近三年（2023–2026）跨平台實戰數據**：
   - 整合 Yahoo 拍賣在線即時競標品、已結標歷史成交與種子歷史庫。
   - 本機收錄 **1,300+ 筆** 結構化卡片數據。
3. **前端極速檢索儀表板 (`index.html`)**：
   - **多維度過濾**：依隊員、年份（2023–2026）、狀態（競標中/已結標）、卡種（唇印/親簽/Patch/特卡）即時篩選。
   - **成員穿透彈窗（Modal Drill-down）**：點擊任一成員卡片，即時彈出該成員專屬三年完整成交履歷。
   - **FB 買賣貼文快貼解析器（Paste & Parse）**：複製社團買賣文貼上，1 秒自動辨識成員名、卡種、限量編號與成交價格。
   - **零依賴免伺服器**：靜態網頁架構，支援 GitHub Pages 免費託管或本地雙擊直接瀏覽。
4. **Python 自動化爬蟲引擎 (`crawler/`)**：
   - 一鍵更新指令：`python run_scanner.py`。

---

## 🚀 快速開始

### 1. 本地直接瀏覽
在瀏覽器中雙擊開啟 `index.html` 即可完整使用全部檢索與過濾功能。

### 2. 更新最新拍賣數據
```bash
python run_scanner.py
```
執行後將自動掃描最新 Yahoo 拍賣商品、更新 `cards.db` 並重新導出 `data/cards_data.js` 與 `data/cards_data.json`。

---

## 📁 目錄結構

```
rakuten-girls-analysis/
├── index.html                   # 前端即時檢索與操盤儀表板 (支援 GitHub Pages)
├── run_scanner.py               # 一鍵更新爬蟲主程式
├── crawler/                     # 爬蟲核心模組
│   ├── yahoo_scanner.py         # Yahoo 拍賣爬蟲
│   ├── members.py               # 27位成員名冊與別名字典
│   ├── card_classifier.py       # 卡種與限量編號分類器
│   ├── seed_history.py          # 2023-2025 種子歷史數據
│   ├── db.py                    # SQLite cards.db 封裝
│   └── export_json.py           # 數據導出模組
├── data/
│   ├── cards_data.js            # 前端免 CORS 離線資料檔
│   └── cards_data.json          # 結構化 JSON 數據檔
├── docs/                        # 架構決策紀錄 (ADR)
└── CONTEXT.md                   # 領域術語規範
```
