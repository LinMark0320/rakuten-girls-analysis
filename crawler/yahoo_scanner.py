# -*- coding: utf-8 -*-
"""
Yahoo 拍賣掃描器。

運作方式（經實際連線 tw.bid.yahoo.com 驗證）：
1. 搜尋結果頁（/search/auction/product）在伺服器端渲染時，會把完整結構化資料內嵌在
   `<script id="isoredux-data" type="mime/invalid">` 標籤中（search.ecsearch.hits /
   ec_priority_items），欄位包含 ec_productid、ec_title、ec_price、ec_numbids、
   ec_endtime、ec_seller、ec_location、ec_item_url 等，遠比解析頁面上的 hashed CSS
   class（styled-components 產生，隨每次部署改變、不穩定）可靠。
2. 純競標格式（有人喊價、倒數結標）的商品，結標下架後不會出現在搜尋結果中，因此對這類商品
   「已結標售出」的判定，是用「前一輪還在 BIDDING、這一輪從搜尋結果消失」來偵測候選商品，
   再單獨對該商品的個別頁面（/item/{id}）發一次請求，讀取同樣內嵌的 isoredux-data JSON
   （item.soldQuantity 等欄位）確認最終是否售出與成交價（見 reconcile_ended_auctions）。
   但直購／一口價格式的賣場商品，賣出後搜尋結果「仍然」會留著這筆刊登，只是 ec_stock_status
   會變成 "0"、ec_buy_count 會 >= 1，因此這類商品在單次掃描當下就能直接判定為真實成交，
   不必等它從搜尋消失（見 _hit_to_card；已比對已知真實成交案例驗證過此訊號可靠）。
   2023–2025 年更早期、已經從兩種搜尋管道都撈不到任何蛛絲馬跡的歷史成交資料，
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

# 收藏圈慣用標記：「純展非賣」是賣家秀收藏、標價是假的展示用數字；
# 「收」「收購」「求購」則是反過來的求購貼文（借用拍賣格式張貼求購訊息，
# 同樣不是真實開價）。兩種都沒有真實成交/開價意義，會嚴重污染行情數據。
_NOT_FOR_SALE_MARKERS = ("純展非賣", "非賣品", "「收」", "收購", "求購")

# 部分成員別名（如「Kira」「Michelle」「Kaho」）本身是常見英文字/名字，關鍵字搜尋
# 放寬成「{member} 卡」後，容易撞名撈到完全無關的商品（實測發現過 NBA 球員卡
# 「Kira Lewis JR.」、精品包型號「Kira 鏈條小包」）。因此比對到成員別名後，還要求
# 標題同時出現團名相關字眼才收錄——真正的樂天女孩卡標題幾乎都會寫團名，此規則
# 不太會誤傷真實資料，卻能把撞名雜訊擋掉。
#
# 除了樂天女孩本隊，成員本人跨隊客串其他啦啦隊/應援團發行的卡也一併收錄
# （見 CONTEXT.md「Cross-Squad Card」）——已逐一查證這些名字組合裡的成員
# 都是同一人跨隊接案，不是撞名：
#   慕獅女孩 Muse Girls（新竹攻城獅）：彭彭、岱縈、熊霓
#   桃氣女孩 Peach Girls（桃園雲豹飛將）：林穎樂、禹菡、金佳垠
#   臺北伊斯特 Tokki Cutie：高橋佳帆
#   樂天桃猿啦啦女孩 CHEER LEADER（2023 舊系列名）：禹菡、凱伊，其實就是樂天女孩本隊
# 「Lamigirls / Lamigo」是樂天桃猿 2020 年由 Rakuten 冠名前的舊隊名，同樣視為本隊歷史資料。
#
# 唯一例外：「笑笑」對到的「中信兄弟 passion sisters」已查證是撞名、不同人（樂天女孩的
# 笑笑是劉姿妤，2025 年才從電豹女跳槽過來；passion sisters 的笑笑 2022 年就在、2023 年
# 就離隊，時間線對不上），所以刻意不把 passion sisters／中信兄弟 加進這份清單。
#
# 「樂天」單獨一個詞也放進來了：有賣家固定用「樂天 {member} ... brg 10級鑑定卡 ...簽名卡」
# 這種模板標題、沒寫「樂天女孩」也沒寫「樂天桃猿」。代價是「樂天」本身也是樂天集團
# 通用品牌字（樂天市場、樂天Kobo 等），理論上仍有極小機率撞到不相關的樂天系商品，
# 這是已知取捨、經使用者確認可接受。
_GROUP_ANCHOR_TERMS = (
    "樂天女孩", "樂天桃猿", "樂天", "啦啦隊", "啦啦女孩", "rkg", "rakuten girls",
    "lamigirls", "lamigo",
    "慕獅女孩", "muse girls",
    "桃氣女孩", "peach girls",
    "臺北伊斯特", "台北伊斯特", "tokki cutie",
)

# 「樂天女孩」偶爾會被賣家打成「樂天 女孩卡」（中間多一個空格），額外用正則兼容
_GROUP_ANCHOR_SPACED_RE = re.compile(r"樂天\s*女孩")


def _has_group_anchor(title: str) -> bool:
    lowered = title.lower()
    if any(term in lowered for term in _GROUP_ANCHOR_TERMS):
        return True
    return bool(_GROUP_ANCHOR_SPACED_RE.search(title))


# 依序比對，判斷這張卡實際上是哪個品牌發行的（見 CONTEXT.md「Cross-Squad Card」
# 「Legacy Branding」）。_has_group_anchor 通過後才會呼叫這個函式，所以命中不到
# 任何規則時，預設值就是樂天女孩本隊。
_SQUAD_BRAND_RULES = (
    ("Lamigirls（舊名）", ("lamigirls", "lamigo")),
    ("慕獅女孩 Muse Girls", ("慕獅女孩", "muse girls")),
    ("桃氣女孩 Peach Girls", ("桃氣女孩", "peach girls")),
    ("臺北伊斯特 Tokki Cutie", ("臺北伊斯特", "台北伊斯特", "tokki cutie")),
)


def classify_squad_brand(title: str) -> str:
    lowered = title.lower()
    for brand, markers in _SQUAD_BRAND_RULES:
        if any(m in lowered for m in markers):
            return brand
    return "樂天女孩"

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

    if any(marker in title for marker in _NOT_FOR_SALE_MARKERS):
        return None

    # 賣場常見「多人整套／全隊合售」大量出貨標題，一次會提到 3 位以上不同成員，
    # 標題上的單一總價其實是整套的價格，不能算成任何一位成員的單卡行情，
    # 這種會嚴重污染定價數據，直接排除不收錄。
    if len(all_matched_members(title)) >= 3:
        return None

    member = normalize_member(title)
    if member is None:
        return None

    if not _has_group_anchor(title):
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

    # 直購／一口價賣場商品賣出後，Yahoo 拍賣搜尋結果「仍然」會留著這筆刊登（跟純競標格式
    # 結標即從搜尋消失不同），差別只在 ec_stock_status 會變成 "0"（庫存歸零）且
    # ec_buy_count 會 >= 1（已被買走過）。經實測比對過已知真實成交案例（高佳彬 8/10 親簽卡
    # #101763207119）完全吻合，因此掃描階段就能直接判定為真實成交，不必等 reconcile 流程。
    stock_status = hit.get("ec_stock_status")
    buy_count_raw = str(hit.get("ec_buy_count") or "0").strip()
    is_confirmed_sold_out = stock_status == "0" and buy_count_raw not in ("", "0")
    status = db.STATUS_SOLD if is_confirmed_sold_out else db.STATUS_BIDDING

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
        "status": status,
        "card_type": classifier_hit,
        "squad_brand": classify_squad_brand(title),
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
    # 原本關鍵字是「{member} 樂天女孩 卡」，但 Yahoo 拍賣搜尋對多詞查詢採「全部詞都要命中」，
    # 只要賣家標題寫的是英文「Rakuten Girls」而非中文「樂天女孩」（實測常見），整筆商品就會被
    # 搜尋引擎排除、翻幾頁都找不到（已實測驗證：單獨搜成員名有結果，加上「樂天女孩」後同一筆消失）。
    # 改成只留「{member} 卡」，靠 _hit_to_card 內建的 normalize_member 嚴格別名比對 + 多人合售
    # 排除規則做二次過濾，噪音沒有明顯增加，但能撈到這整類漏網商品。
    keyword = f"{member} 卡"

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
