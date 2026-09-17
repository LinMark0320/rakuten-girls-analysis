# -*- coding: utf-8 -*-
"""
種子資料匯入。

重要說明（對應 implementation_plan.md 的驗證計畫修正）：
這裡只匯入「已知確實存在、有真實 Yahoo 拍賣商品編號可供核對」的紀錄——也就是
index.html 既有內容中，本來就標註了 Yahoo 商品 ID（#101763207119 等）的 7 筆
2026 年即時競標／成交案例。這些編號已透過實際連線 tw.bid.yahoo.com 核對存在。

刻意「不」捏造 2023–2025 年的具體成交紀錄：index.html 現有內容裡，該時間範圍
只有籠統的價格區間（如「孟潔 NT$2,500~3,200」），沒有對應的商品編號或確切成交日期，
若在此編造成假的個別成交紀錄，會污染資料庫、誤導賣家定價決策。
2023–2025 年的真實歷史成交，應透過前端「FB 貼文智慧快貼解析器」或使用者手動
輸入實際的成交截圖/連結來補完，而不是由程式假造。
"""
from crawler import db
from crawler.members import normalize_member
from crawler.card_classifier import classify_card_type, extract_serial_number

# (member, title, price, num_bids, status, item_id, seller_name, seller_location, year)
_SEED_ROWS = [
    ("高佳彬", "2026 新人親簽卡 8/10 (普通隊服簽) 高佳彬", 6600, 1,
     db.STATUS_SOLD, "101763207119", None, "高雄市", 2026),
    ("高佳彬", "2026 女孩唇印親簽卡 高佳彬 (限量 2/5)", 7500, 21,
     db.STATUS_BIDDING, "101762875949", None, None, 2026),
    ("林穎樂", "2026 女僕用品親簽卡【首號大頭貼 1/10】林穎樂", 6012, 29,
     db.STATUS_BIDDING, "101762873559", None, None, 2026),
    ("若潼", "2026 女僕拉鍊 Patch 1/1 金簽 (頂級神物) 若潼", 8000, 49,
     db.STATUS_BIDDING, "101762971421", None, None, 2026),
    ("廉世彬", "2026 夏日泳裝 SP 簽名卡 廉世彬 限量 10/10 (尾號)", 3456, 25,
     db.STATUS_BIDDING, "101762824141", None, None, 2026),
    ("禹洙漢", "2026 女僕親簽卡 禹洙漢 (限量 18/25)", 1850, 13,
     db.STATUS_BIDDING, "101762877080", None, None, 2026),
    ("琳妲", "2026 夏日泳裝用品親簽卡 琳妲 (限量 02/10)", 1350, 8,
     db.STATUS_BIDDING, "101762875563", None, None, 2026),
    ("孟潔", "【孟潔】【隊服】【唇印簽名卡】【首號大頭貼】2026 Rakuten Girls 年度女孩卡 女孩唇印親簽卡 01/05",
     700, 6, db.STATUS_BIDDING, "101763177939", "阿澤卡舖", None, 2026),
]


def build_seed_cards() -> list[dict]:
    cards = []
    for member, title, price, num_bids, status, item_id, seller_name, seller_location, year in _SEED_ROWS:
        assert normalize_member(title) == member, f"別名比對不到「{member}」：{title}"
        serial = extract_serial_number(title) or {}
        cards.append({
            "platform_item_id": item_id,
            "platform": "yahoo",
            "member_name": member,
            "year": year,
            "title": title,
            "price": price,
            "num_bids": num_bids,
            "status": status,
            "card_type": classify_card_type(title),
            "serial_number": serial.get("serial_number"),
            "is_first_num": serial.get("is_first_num", False),
            "is_last_num": serial.get("is_last_num", False),
            "image_url": None,
            "item_url": f"https://tw.bid.yahoo.com/item/{item_id}",
            "seller_name": seller_name,
            "seller_location": seller_location,
            "source": "seed",
        })
    return cards


def seed(db_path=None) -> int:
    conn = db.get_connection(db_path) if db_path else db.get_connection()
    db.init_db(conn)
    count = 0
    for card in build_seed_cards():
        outcome = db.upsert_card(conn, card, touch_last_seen=False)
        if outcome == "inserted":
            count += 1
    conn.close()
    return count


if __name__ == "__main__":
    n = seed()
    print(f"種子資料匯入完成，新增 {n} 筆。")
