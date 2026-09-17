# Rakuten Girls Card Market Intelligence (樂天女孩卡二級市場行情監測)

本系統負責追蹤與監控樂天女孩（Rakuten Girls）27位主要在籍成員之收藏卡在各平台（Yahoo拍賣、Facebook社團等）的即時競標與近三年歷史成交數據，為卡舖賣家提供精準定價決策。

## Language

### Core Entities

**Member (隊員 / 成員)**:
經官方確認之現役主要樂天女孩啦啦隊在籍成員（排除行政幹部如團長、MC、總監）。
_Avoid_: 女孩, 網紅, 幹部, 小姐

**Card (收藏卡)**:
官方正式發行、具備卡種分類與防偽認證的實體球員/女孩收藏卡（如親簽卡、唇印卡、用品卡、特卡、RC卡）。
_Avoid_: 周邊, 商品, 雜物, 紀念品

**Autograph Card (親簽卡)**:
由成員親筆簽名之限量特卡。
_Avoid_: 簽名品, 簽名周邊

**Lip Print Card (唇印卡)**:
帶有成員真實唇印及親筆簽名之頂級極限量卡種，全系列發行量極低（如 /05）。
_Avoid_: 口紅卡, 吻印卡

**Serial Number (限量編號)**:
卡面上壓印之獨立限量分數（如 01/05、08/10、18/25），用以界定首號（01）、尾號與普通號之稀缺性。
_Avoid_: 編號, 序號, 號碼

### Market Data & Crawler Entities

**Listing (拍賣刊登)**:
各大拍賣平台上正在進行投標或提供直購的活躍拍賣商品（Status: ACTIVE）。
_Avoid_: 貼文, 貨品, 賣場

**Transaction (成交紀錄)**:
已確認結標售出、具備具體交易金額與成交時間的歷史數據（Status: SOLD / COMPLETED）。
_Avoid_: 訂單, 歷史, 買賣

**Platform Source (平台來源)**:
產生刊登或成交數據的二級市場平台（Yahoo拍賣、Facebook公開社團、蝦皮）。
_Avoid_: 網站, 通路

**Crawler Scheduler (爬蟲排程器)**:
後端負責按時或按需觸發拍賣掃描並更新本地資料庫的控制腳本。
_Avoid_: 機器人, 抓取器

**Seed Data (歷史種子資料)**:
系統初始化時預載入之 2023–2025 歷史重大驗證成交數據，確保三年時間窗口完整度。
_Avoid_: 預設資料, 假資料

**Paste-and-Parse (貼文智慧解析器)**:
將複製之 Facebook 買賣社團貼文文字或公開網址自動解析並轉換為結構化卡片成交紀錄之模組。
_Avoid_: 貼文抓取, 貼文複製
