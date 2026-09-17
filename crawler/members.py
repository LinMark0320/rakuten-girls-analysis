# -*- coding: utf-8 -*-
"""
27 位樂天女孩主要在籍成員別名對照字典。
名單與別名來源：index.html 內既有的 members-grid 區塊（維基百科官方「目前成員」表格），
非本模組自行臆測產生，避免張冠李戴。
"""

# 隊員別名多對一字典：canonical name -> 所有可能出現在賣家標題中的別名/藝名/本名/韓文/暱稱
MEMBER_ALIASES = {
    "河智媛": ["河智媛", "하지원", "Hajiwon", "智媛"],
    "禹洙漢": ["禹洙漢", "우수한", "洙漢"],
    "廉世彬": ["廉世彬", "염세빈", "世彬"],
    "高佳彬": ["高佳彬", "고가빈", "GaBeen", "佳彬"],
    "金佳垠": ["金佳垠", "김가은", "佳垠"],
    "孟潔": ["孟潔", "林孟潔"],
    "琳妲": ["琳妲", "林羿禎"],
    "若潼": ["若潼", "李若潼"],
    "岱縈": ["岱縈", "林岱縈"],
    "曲曲": ["曲曲", "凃曲羿"],
    "筠熹": ["筠熹", "鄭筠熹"],
    "崔荷潾": ["崔荷潾", "張梔呈", "梔梔"],
    "林穎樂": ["林穎樂", "林俞廷", "穎樂"],
    "熊霓": ["熊霓", "Michelle"],
    "卉妮": ["卉妮", "涂卉妮"],
    "高橋佳帆": ["高橋佳帆", "Kaho", "佳帆"],
    "笑笑": ["笑笑", "劉姿妤"],
    "彭彭": ["彭彭", "彭柔旂"],
    "宋宋": ["宋宋", "宋婉卉"],
    "貝佳頤": ["貝佳頤", "林儷軒"],
    "凱伊": ["凱伊", "沈珈妤"],
    "穆又甯": ["穆又甯", "邱澄甯", "小紫", "邱紫庭"],
    "蜜卡登": ["蜜卡登", "徐青媞", "Mika"],
    "言梓璇": ["言梓璇", "李昀芯"],
    "禹菡": ["禹菡", "黃詩涵"],
    "溫妮": ["溫妮", "王名韻"],
    "Kira": ["Kira", "詹上真"],
}

assert len(MEMBER_ALIASES) == 27, "樂天女孩主要在籍成員應為 27 位"

# 依別名字串長度由長到短排序，避免短別名（如「佳彬」）搶先誤配到別的成員全名子字串
_SORTED_ALIAS_PAIRS = sorted(
    (
        (alias, canonical)
        for canonical, aliases in MEMBER_ALIASES.items()
        for alias in aliases
    ),
    key=lambda pair: len(pair[0]),
    reverse=True,
)


def normalize_member(text: str) -> str | None:
    """
    在任意文字（賣家商品標題、FB 貼文全文等）中比對出所屬的樂天女孩成員標準名。
    找不到符合的別名時回傳 None。
    """
    if not text:
        return None
    for alias, canonical in _SORTED_ALIAS_PAIRS:
        if alias in text:
            return canonical
    return None


def all_matched_members(text: str) -> list[str]:
    """回傳文字中所有比對到的（不重複）成員標準名，用來偵測多人合售/整套的賣場標題。"""
    if not text:
        return []
    found = []
    for alias, canonical in _SORTED_ALIAS_PAIRS:
        if canonical not in found and alias in text:
            found.append(canonical)
    return found


def all_members() -> list[str]:
    return list(MEMBER_ALIASES.keys())
