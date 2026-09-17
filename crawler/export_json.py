# -*- coding: utf-8 -*-
"""
將 SQLite 資料庫轉換為前端可直接加載的高效能 JSON 檔案。

同時輸出兩份：
  - data/cards_data.json：純 JSON，供除錯或未來若有伺服器環境時 fetch() 使用。
  - data/cards_data.js：包在 `window.RG_CARDS_DATA = {...};` 裡的 JS 檔。
    index.html 用 <script src="data/cards_data.js"> 載入這份——瀏覽器對本機
    file:/// 協議下的 fetch()/XHR 會擋 CORS 而讀不到 .json，但一般 <script src>
    載入本機檔案不受此限，這樣雙擊 index.html 離線開啟時才能正常讀到資料。
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from crawler import db
from crawler.members import all_members

DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "cards_data.json"
DEFAULT_JS_OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "cards_data.js"


def _build_payload(conn) -> dict:
    cards = db.query_cards(conn)
    for card in cards:
        card["is_first_num"] = bool(card["is_first_num"])
        card["is_last_num"] = bool(card["is_last_num"])
        history = db.get_price_history(conn, card["platform_item_id"])
        card["price_history"] = history if len(history) > 1 else []

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_count": len(cards),
        "members": all_members(),
        "cards": cards,
    }


def export_cards(conn, output_path=DEFAULT_OUTPUT_PATH, js_output_path=DEFAULT_JS_OUTPUT_PATH) -> int:
    payload = _build_payload(conn)
    json_text = json.dumps(payload, ensure_ascii=False, indent=None, separators=(",", ":"))

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json_text, encoding="utf-8")

    js_output_path = Path(js_output_path)
    js_output_path.parent.mkdir(parents=True, exist_ok=True)
    js_output_path.write_text(f"window.RG_CARDS_DATA = {json_text};", encoding="utf-8")

    return len(payload["cards"])


if __name__ == "__main__":
    _conn = db.get_connection()
    db.init_db(_conn)
    n = export_cards(_conn)
    print(f"已匯出 {n} 筆卡片資料至 {DEFAULT_OUTPUT_PATH} 與 {DEFAULT_JS_OUTPUT_PATH}")
    _conn.close()
