# -*- coding: utf-8 -*-
"""
本機 SQLite 資料庫模組：定義 cards / price_history 架構，提供去重、增量寫入與查詢方法。
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "cards.db"

STATUS_BIDDING = "BIDDING"
STATUS_SOLD = "SOLD"
STATUS_ENDED_UNSOLD = "ENDED_UNSOLD"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    platform_item_id TEXT PRIMARY KEY,
    platform         TEXT NOT NULL DEFAULT 'yahoo',
    member_name      TEXT NOT NULL,
    year             INTEGER,
    title            TEXT NOT NULL,
    price            INTEGER,
    num_bids         INTEGER DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'BIDDING',
    card_type        TEXT,
    squad_brand      TEXT DEFAULT '樂天女孩',
    serial_number    TEXT,
    is_first_num     INTEGER DEFAULT 0,
    is_last_num      INTEGER DEFAULT 0,
    image_url        TEXT,
    item_url         TEXT,
    seller_name      TEXT,
    seller_location  TEXT,
    source           TEXT DEFAULT 'yahoo_scanner',
    last_seen_at     TEXT,
    miss_count       INTEGER DEFAULT 0,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS price_history (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_item_id  TEXT NOT NULL REFERENCES cards(platform_item_id),
    price             INTEGER,
    num_bids          INTEGER,
    status            TEXT,
    recorded_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cards_member ON cards(member_name);
CREATE INDEX IF NOT EXISTS idx_cards_year ON cards(year);
CREATE INDEX IF NOT EXISTS idx_cards_status ON cards(status);
CREATE INDEX IF NOT EXISTS idx_price_history_item ON price_history(platform_item_id);
"""

_CARD_COLUMNS = [
    "platform_item_id", "platform", "member_name", "year", "title", "price",
    "num_bids", "status", "card_type", "squad_brand", "serial_number", "is_first_num",
    "is_last_num", "image_url", "item_url", "seller_name", "seller_location",
    "source",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_connection(db_path=DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    # squad_brand 是後來才加的欄位，既有的 cards.db 不會因為上面的
    # CREATE TABLE IF NOT EXISTS 自動補上，需要額外遷移一次。
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(cards)")}
    if "squad_brand" not in existing_cols:
        conn.execute("ALTER TABLE cards ADD COLUMN squad_brand TEXT DEFAULT '樂天女孩'")
    conn.commit()


def upsert_card(conn: sqlite3.Connection, card: dict, touch_last_seen: bool = True) -> str:
    """
    以 platform_item_id 去重：不存在則新增，存在則更新。
    當 price 或 num_bids 有變化時，於 price_history 補一筆紀錄，藉此追蹤出價隨時間推移之漲升歷程。
    touch_last_seen=True（預設，Yahoo 即時掃描使用）代表這筆資料剛剛在一次實際掃描中被看到，
    會更新 last_seen_at 並將 miss_count 歸零；種子資料／FB 貼文解析屬於非即時掃描來源，
    呼叫時應傳入 touch_last_seen=False，避免這些從未被爬蟲實際掃到過的商品被誤判為「已消失」。
    回傳 'inserted' 或 'updated' 或 'unchanged'。
    """
    item_id = card["platform_item_id"]
    row = conn.execute(
        "SELECT price, num_bids, status FROM cards WHERE platform_item_id = ?",
        (item_id,),
    ).fetchone()
    now = _now()
    last_seen_at = now if touch_last_seen else None

    # SOLD / ENDED_UNSOLD 是靠讀取商品詳情頁（isoredux item.soldQuantity）才能確認的終局狀態，
    # 比「這個商品又出現在搜尋結果裡了」這種訊號可靠得多——Yahoo 拍賣的公開搜尋索引本身並不
    # 保證某商品「還能再買到」就代表它從沒被賣出過（同一刊登可能還有其他庫存、或被重新上架）。
    # 因此例行掃描帶著 status=BIDDING 進來時，不能反過來把已確認的終局狀態蓋回去。
    if row is not None and row["status"] in (STATUS_SOLD, STATUS_ENDED_UNSOLD) and card.get("status") == STATUS_BIDDING:
        if touch_last_seen:
            conn.execute(
                "UPDATE cards SET last_seen_at = ? WHERE platform_item_id = ?", (now, item_id)
            )
            conn.commit()
        return "unchanged"

    if row is None:
        values = {col: card.get(col) for col in _CARD_COLUMNS}
        values["is_first_num"] = int(bool(values.get("is_first_num")))
        values["is_last_num"] = int(bool(values.get("is_last_num")))
        placeholders = ", ".join(f":{c}" for c in _CARD_COLUMNS)
        columns = ", ".join(_CARD_COLUMNS)
        conn.execute(
            f"INSERT INTO cards ({columns}, last_seen_at, miss_count, created_at, updated_at) "
            f"VALUES ({placeholders}, :last_seen_at, 0, :created_at, :updated_at)",
            {**values, "last_seen_at": last_seen_at, "created_at": now, "updated_at": now},
        )
        conn.execute(
            "INSERT INTO price_history (platform_item_id, price, num_bids, status, recorded_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (item_id, card.get("price"), card.get("num_bids"), card.get("status"), now),
        )
        conn.commit()
        return "inserted"

    price_changed = row["price"] != card.get("price")
    bids_changed = row["num_bids"] != card.get("num_bids")
    status_changed = row["status"] != card.get("status")

    if not (price_changed or bids_changed or status_changed):
        if touch_last_seen:
            conn.execute(
                "UPDATE cards SET last_seen_at = ?, miss_count = 0 WHERE platform_item_id = ?",
                (now, item_id),
            )
        conn.commit()
        return "unchanged"

    update_cols = [c for c in _CARD_COLUMNS if c != "platform_item_id"]
    set_clause = ", ".join(f"{c} = :{c}" for c in update_cols)
    values = {col: card.get(col) for col in _CARD_COLUMNS}
    values["is_first_num"] = int(bool(values.get("is_first_num")))
    values["is_last_num"] = int(bool(values.get("is_last_num")))
    last_seen_clause = ", last_seen_at = :last_seen_at, miss_count = 0" if touch_last_seen else ""
    conn.execute(
        f"UPDATE cards SET {set_clause}, updated_at = :updated_at{last_seen_clause} "
        f"WHERE platform_item_id = :platform_item_id",
        {**values, "updated_at": now, "last_seen_at": last_seen_at},
    )
    conn.execute(
        "INSERT INTO price_history (platform_item_id, price, num_bids, status, recorded_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (item_id, card.get("price"), card.get("num_bids"), card.get("status"), now),
    )
    conn.commit()
    return "updated"


# 連續幾次掃描都未在搜尋結果中出現，才視為候選「可能已結標」商品。
# 避免單次掃描因關鍵字排序/分頁波動而誤判仍在架商品已下架。
RECONCILE_MISS_THRESHOLD = 2


def get_reconcile_candidates(conn: sqlite3.Connection, member_name: str) -> set:
    """
    取得「已被即時掃描實際看過至少一次、且目前狀態仍是 BIDDING」的商品 ID 集合。
    只有這個集合裡的商品，才有資格因為「這輪掃描又沒看到」而被記一次 miss，
    尚未有 last_seen_at（例如種子資料或 FB 貼文解析新增的商品）一律不在候選名單中。
    """
    rows = conn.execute(
        "SELECT platform_item_id FROM cards "
        "WHERE status = ? AND member_name = ? AND last_seen_at IS NOT NULL",
        (STATUS_BIDDING, member_name),
    ).fetchall()
    return {r["platform_item_id"] for r in rows}


def record_miss(conn: sqlite3.Connection, item_id: str) -> int:
    """商品這輪掃描沒被看到，miss_count + 1，回傳最新的 miss_count。"""
    conn.execute(
        "UPDATE cards SET miss_count = miss_count + 1 WHERE platform_item_id = ?",
        (item_id,),
    )
    conn.commit()
    row = conn.execute(
        "SELECT miss_count FROM cards WHERE platform_item_id = ?", (item_id,)
    ).fetchone()
    return row["miss_count"] if row else 0


def mark_card_status(conn: sqlite3.Connection, item_id: str, status: str, final_price=None) -> None:
    now = _now()
    if final_price is not None:
        conn.execute(
            "UPDATE cards SET status = ?, price = ?, updated_at = ? WHERE platform_item_id = ?",
            (status, final_price, now, item_id),
        )
    else:
        conn.execute(
            "UPDATE cards SET status = ?, updated_at = ? WHERE platform_item_id = ?",
            (status, now, item_id),
        )
    conn.execute(
        "INSERT INTO price_history (platform_item_id, price, num_bids, status, recorded_at) "
        "SELECT platform_item_id, price, num_bids, status, ? FROM cards WHERE platform_item_id = ?",
        (now, item_id),
    )
    conn.commit()


def query_cards(conn: sqlite3.Connection, member_name=None, year=None, status=None, card_type=None):
    sql = "SELECT * FROM cards WHERE 1=1"
    params = []
    if member_name:
        sql += " AND member_name = ?"
        params.append(member_name)
    if year:
        sql += " AND year = ?"
        params.append(year)
    if status:
        sql += " AND status = ?"
        params.append(status)
    if card_type:
        sql += " AND card_type = ?"
        params.append(card_type)
    sql += " ORDER BY updated_at DESC"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_price_history(conn: sqlite3.Connection, item_id: str):
    rows = conn.execute(
        "SELECT price, num_bids, status, recorded_at FROM price_history "
        "WHERE platform_item_id = ? ORDER BY recorded_at ASC",
        (item_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def count_cards(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM cards").fetchone()["n"]
