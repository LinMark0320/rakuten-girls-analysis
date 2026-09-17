# -*- coding: utf-8 -*-
"""
Yahoo 拍賣掃描器。

運作方式（經實際連線 tw.bid.yahoo.com 驗證）：
1. 搜尋結果頁（/search/auction/product）在伺服器端渲染時，會把完整結構化資料內嵌在
   `<script id="isoredux-data" type="mime/invalid">` 標籤中（search.ecsearch.hits /
   ec_priority_items），欄位包含 ec_productid、ec_title、ec_price、ec_numbids、
   ec_endtime、ec_seller、ec_location、ec_item_url 等，遠比解析頁面上的 hashed CSS
   class（styled-components 產生，隨每次部署改變、不穩定）可靠。
2. Yahoo 拍賣公開搜尋只索引「目前仍上架」的商品，已結標下架的拍賣不會出現在搜尋結果中，
   因此本掃描器對「已結標售出」的判定，是用「前一輪還在 BIDDING、這一輪從搜尋結果消失」
   來偵測候選商品，再單獨對該商品的個別頁面（/item/{id}）發一次請求，讀取同樣內嵌的
   isoredux-data JSON（item.soldQuantity 等欄位）確認最終是否售出與成交價。
   2023–2025 年的歷史成交資料，本來就不可能從「目前上架中」的搜尋結果反推得到，
   仍須仰賴 seed_history.py 與前端 FB 貼文解析器補完（見 ADR 0001）。
"""
import argparse
import json
import re
import time
import random
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from crawler import db
from crawler.members import MEMBER_ALIASES, normalize_member, all_matched_members, all_members
from crawler.card_classifier import classify_card_type, extract_serial_number

SEARCH_URL = "https://tw.bid.yahoo.com/search/auction/product"
ITEM_URL = "https://tw.bid.yahoo.com/item/{item_id}"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_ISOREDUX_RE = re.compile(
    r'isoredux-data"\s+type="mime/invalid">(.*?)</script>', re.S
)
_YEAR_RE = re.compile(r"\b(202[3-6])\b")

# 「偶像、球員卡與郵幣」相關類目，僅供過濾雜物用的輔助訊號，不作為唯一硬性條件
_CARD_CATEGORY_IDS = {"2092107302", "20992", "2092073959", "2092073961"}

REQUEST_TIMEOUT = 15
MIN_DELAY_SEC = 1.5
MAX_DELAY_SEC = 3.0


def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "zh-TW,zh;q=0.9"})
    return s


def _polite_sleep():
    time.sleep(random.uniform(MIN_DELAY_SEC, MAX_DELAY_SEC))


def _extract_isoredux(html: str) -> dict:
    m = _ISOREDUX_RE.search(html)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def _guess_year(title: str, submittime) -> int:
    m = _YEAR_RE.search(title)
    if m:
        return int(m.group(1))
    if submittime:
        try:
            return datetime.fromtimestamp(int(submittime), tz=timezone.utc).year
        except (ValueError, OSError):
            pass
    return datetime.now(timezone.utc).year


def _to_int_price(*candidates) -> int:
    for c in candidates:
        if c in (None, ""):
            continue
        try:
            return int(float(c))
        except (TypeError, ValueError):
            continue
    return 0


def _hit_to_card(hit: dict) -> dict | None:
    """
    只有標題確實命中 27 位成員別名字典其中之一時，才視為有效卡片並歸戶到該成員。
    即使是用「某成員 樂天女孩 卡」關鍵字搜到的結果，也不會盲目歸戶到搜尋關鍵字對應
    的成員身上——Yahoo 拍賣關鍵字搜尋本來就會混入不精確的相關商品，若無腦 fallback
    會把根本沒提到該成員的雜物也算進她名下，污染資料庫。
    """
    title = hit.get("ec_title") or ""
    if not title:
        return None

    # 賣場常見「多人整套／全隊合售」大量出貨標題，一次會提到 3 位以上不同成員，
    # 標題上的單一總價其實是整套的價格，不能算成任何一位成員的單卡行情，
    # 這種會嚴重污染定價數據，直接排除不收錄。
    if len(all_matched_members(title)) >= 3:
        return None

    member = normalize_member(title)
    if member is None:
        return None

    item_id = hit.get("ec_productid")
    item_url = hit.get("ec_item_url") or ""
    if not item_id and item_url:
        m = re.search(r"/item/(\d+)", item_url)
        item_id = m.group(1) if m else None
    if not item_id:
        return None

    num_bids_raw = hit.get("ec_numbids")
    num_bids = int(num_bids_raw) if str(num_bids_raw).strip().isdigit() else 0
    price = _to_int_price(hit.get("ec_price"), hit.get("ec_buyprice"), hit.get("ec_listprice"))

    classifier_hit = classify_card_type(title)
    serial = extract_serial_number(title) or {}

    return {
        "platform_item_id": str(item_id),
        "platform": "yahoo",
        "member_name": member,
        "year": _guess_year(title, hit.get("ec_submittime")),
        "title": title,
        "price": price,
        "num_bids": num_bids,
        "status": db.STATUS_BIDDING,
        "card_type": classifier_hit,
        "serial_number": serial.get("serial_number"),
        "is_first_num": serial.get("is_first_num", False),
        "is_last_num": serial.get("is_last_num", False),
        "image_url": hit.get("ec_img_uri"),
        "item_url": item_url or ITEM_URL.format(item_id=item_id),
        "seller_name": hit.get("ec_storename") or hit.get("ec_seller"),
        "seller_location": hit.get("ec_location"),
        "source": "yahoo_scanner",
    }


def search_member(session: requests.Session, member: str, max_pages: int = 2):
    """對單一成員關鍵字搜尋，回傳解析後的卡片 dict 清單（跨頁彙整、已去重）。"""
    seen_ids = set()
    results = []
    keyword = f"{member} 樂天女孩 卡"

    for page in range(max_pages):
        params = {"p": keyword, "s1": "new", "o1": "d"}
        if page > 0:
            params["b"] = page * 60 + 1
        try:
            resp = session.get(SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"  [WARN] 搜尋「{keyword}」第 {page + 1} 頁失敗：{exc}")
            break

        data = _extract_isoredux(resp.text)
        ecsearch = (data.get("search") or {}).get("ecsearch") or {}
        hits = (ecsearch.get("ec_priority_items") or []) + (ecsearch.get("hits") or [])
        if not hits:
            break

        for hit in hits:
            card = _hit_to_card(hit)
            if card is None or card["platform_item_id"] in seen_ids:
                continue
            seen_ids.add(card["platform_item_id"])
            results.append(card)

        total = ecsearch.get("totalhitcount") or 0
        if (page + 1) * 60 >= total:
            break
        _polite_sleep()

    return results


def fetch_item_detail(session: requests.Session, item_id: str) -> dict | None:
    """讀取單一商品頁的 isoredux-data，用來確認拍賣是否已結標售出（見模組說明）。"""
    try:
        resp = session.get(ITEM_URL.format(item_id=item_id), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  [WARN] 讀取商品 {item_id} 詳情失敗：{exc}")
        return None

    data = _extract_isoredux(resp.text)
    item = data.get("item") or {}
    if not item:
        return None

    bid_info = item.get("bidInfo") or {}
    sold_qty = item.get("soldQuantity") or 0
    if sold_qty > 0:
        final_price = bid_info.get("currentPrice") or item.get("price")
        return {"status": db.STATUS_SOLD, "final_price": _to_int_price(final_price)}
    return {"status": db.STATUS_ENDED_UNSOLD, "final_price": None}


def reconcile_ended_auctions(session: requests.Session, conn, member: str, seen_ids: set):
    """
    比對資料庫中該成員原本 BIDDING、但這輪掃描沒在搜尋結果內看到的商品。
    只有連續 miss 達 db.RECONCILE_MISS_THRESHOLD 次（預設 2）才會真的去讀該商品的
    詳情頁確認最終狀態，單次掃描的排序/分頁波動只會記一次 miss、不會馬上判定已結標。
    """
    candidates = db.get_reconcile_candidates(conn, member_name=member)
    missing_this_run = candidates - seen_ids
    for item_id in missing_this_run:
        miss_count = db.record_miss(conn, item_id)
        if miss_count < db.RECONCILE_MISS_THRESHOLD:
            continue
        _polite_sleep()
        outcome = fetch_item_detail(session, item_id)
        if outcome is None:
            continue
        db.mark_card_status(conn, item_id, outcome["status"], final_price=outcome["final_price"])
        print(f"  [RECONCILE] {item_id} -> {outcome['status']}"
              + (f" (${outcome['final_price']})" if outcome["final_price"] else ""))


def run_scan(conn, members=None, max_pages: int = 2, reconcile: bool = True):
    members = members or all_members()
    session = _session()
    stats = {"inserted": 0, "updated": 0, "unchanged": 0}

    for i, member in enumerate(members):
        print(f"[{i + 1}/{len(members)}] 掃描「{member}」...")
        cards = search_member(session, member, max_pages=max_pages)
        seen_ids = set()
        for card in cards:
            seen_ids.add(card["platform_item_id"])
            outcome = db.upsert_card(conn, card)
            stats[outcome] = stats.get(outcome, 0) + 1
        print(f"  -> 抓到 {len(cards)} 筆相關商品")

        if reconcile:
            reconcile_ended_auctions(session, conn, member, seen_ids)

        _polite_sleep()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Yahoo 拍賣樂天女孩卡片掃描器")
    parser.add_argument("--member", help="只掃描單一成員（預設掃描全部 27 位）")
    parser.add_argument("--max-pages", type=int, default=2, help="每位成員最多翻幾頁搜尋結果（每頁約 60 筆）")
    parser.add_argument("--no-reconcile", action="store_true", help="略過已消失拍賣的結標狀態確認")
    parser.add_argument("--db-path", default=str(db.DEFAULT_DB_PATH))
    args = parser.parse_args()

    if args.member and args.member not in MEMBER_ALIASES:
        parser.error(f"未知成員「{args.member}」，可用名單：{', '.join(all_members())}")

    conn = db.get_connection(args.db_path)
    db.init_db(conn)

    members = [args.member] if args.member else None
    stats = run_scan(conn, members=members, max_pages=args.max_pages, reconcile=not args.no_reconcile)

    print(f"完成。新增 {stats.get('inserted', 0)} 筆、更新 {stats.get('updated', 0)} 筆、"
          f"無變化 {stats.get('unchanged', 0)} 筆。資料庫目前共 {db.count_cards(conn)} 筆。")
    conn.close()


if __name__ == "__main__":
    main()
