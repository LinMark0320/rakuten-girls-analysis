# -*- coding: utf-8 -*-
"""
一鍵主入口：初始化 DB -> 注入種子資料 -> 執行 Yahoo 即時掃描 -> 匯出 cards_data.json。
可手動執行，亦可供 Windows工作排程器定期呼叫：
    python run_scanner.py
    python run_scanner.py --max-pages 3
    python run_scanner.py --skip-scan   # 只重新匯出 JSON，不打 Yahoo
"""
import argparse
import sys

from crawler import db, seed_history, export_json, yahoo_scanner


def main():
    parser = argparse.ArgumentParser(description="樂天女孩卡片行情監控 - 一鍵執行")
    parser.add_argument("--max-pages", type=int, default=2, help="Yahoo 每位成員最多翻幾頁搜尋結果")
    parser.add_argument("--skip-scan", action="store_true", help="略過 Yahoo 即時掃描，只重新匯出 JSON")
    parser.add_argument("--skip-seed", action="store_true", help="略過種子資料匯入")
    args = parser.parse_args()

    conn = db.get_connection()
    db.init_db(conn)
    print(f"[1/4] 資料庫初始化完成：{db.DEFAULT_DB_PATH}")

    if not args.skip_seed:
        n = seed_history.seed()
        print(f"[2/4] 種子資料匯入完成，新增 {n} 筆。")
    else:
        print("[2/4] 已略過種子資料匯入。")

    if not args.skip_scan:
        print("[3/4] 開始 Yahoo 拍賣即時掃描（27 位成員，請耐心等候，過程中會禮貌性延遲避免過度請求）...")
        stats = yahoo_scanner.run_scan(conn, max_pages=args.max_pages)
        print(f"       新增 {stats.get('inserted', 0)} 筆、更新 {stats.get('updated', 0)} 筆、"
              f"無變化 {stats.get('unchanged', 0)} 筆。")
    else:
        print("[3/4] 已略過 Yahoo 即時掃描。")

    total = db.count_cards(conn)
    n_exported = export_json.export_cards(conn)
    print(f"[4/4] 已匯出 {n_exported} 筆卡片資料至 {export_json.DEFAULT_OUTPUT_PATH}")
    print(f"完成。資料庫目前共 {total} 筆卡片紀錄。")
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
