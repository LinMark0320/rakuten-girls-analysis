# -*- coding: utf-8 -*-
"""
卡種特徵自動辨識引擎：從商品標題／描述文字中打上結構化卡種標籤，
並萃取限量編號（serial number），標註首號／尾號。
"""
import re

LIP_PRINT = "LIP_PRINT"
AUTOGRAPH = "AUTOGRAPH"
PATCH_MEMORABILIA = "PATCH_MEMORABILIA"
SPECIAL_INSERT = "SPECIAL_INSERT"
UNSPECIFIED = "UNSPECIFIED"

# 由高到低優先權：越前面的類型一旦命中即視為該卡片的主要卡種
_CARD_TYPE_RULES = [
    (LIP_PRINT, ("唇印",)),
    (PATCH_MEMORABILIA, ("球衣", "用品卡", "拉鍊", "patch", "Patch", "PATCH", "實物卡")),
    (SPECIAL_INSERT, ("睡衣", "女僕", "泳裝", "鑑定卡", "PSA", "BGS", r"\bSP\b", r"\bRC\b")),
    (AUTOGRAPH, ("親簽", "親筆簽名", "簽名卡", "簽名", "autograph", "Autograph")),
]


def classify_card_type(text: str) -> str:
    if not text:
        return UNSPECIFIED
    for card_type, keywords in _CARD_TYPE_RULES:
        for kw in keywords:
            if kw.startswith("\\b"):
                if re.search(kw, text, flags=re.IGNORECASE):
                    return card_type
            elif kw in text:
                return card_type
    return UNSPECIFIED


# 限量編號：01/05、8/10、18/25、1/1 …（全形／半形斜線皆可），分子分母限制在 1~999
# 避免誤吃日期或背號等不相關數字
_SERIAL_RE = re.compile(r"(?<!\d)(\d{1,3})\s*[/／]\s*(\d{1,3})(?!\d)")


def extract_serial_number(text: str):
    """
    回傳 (serial_number:str, is_first_num:bool, is_last_num:bool) 或找不到時回傳 None。
    """
    if not text:
        return None
    for match in _SERIAL_RE.finditer(text):
        num, denom = int(match.group(1)), int(match.group(2))
        if num == 0 or denom == 0 or num > denom:
            continue
        serial = f"{match.group(1)}/{match.group(2)}"
        return {
            "serial_number": serial,
            "is_first_num": num == 1,
            "is_last_num": num == denom,
        }
    return None
