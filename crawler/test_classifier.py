# -*- coding: utf-8 -*-
"""
對應 implementation_plan.md 驗證計畫：檢查隊員姓名比對與卡種萃取率的正規化精確度。
執行：python -m pytest crawler/test_classifier.py -v
"""
from crawler.members import normalize_member, all_matched_members
from crawler.card_classifier import classify_card_type, extract_serial_number, LIP_PRINT, AUTOGRAPH


def test_member_alias_matching():
    assert normalize_member("【孟潔】01/05 唇印親簽卡 首號大頭貼") == "孟潔"
    assert normalize_member("2026 高佳彬 8/10 新人親簽卡") == "高佳彬"
    assert normalize_member("若潼 女僕拉鍊 Patch 1/1 金簽") == "若潼"
    # 韓文/暱稱別名也要能歸戶到正確的中文標準名
    assert normalize_member("고가빈 唇印卡") == "高佳彬"
    assert normalize_member("崔荷潾 梔梔 應援卡") == "崔荷潾"
    assert normalize_member("完全不相干的商品標題") is None


def test_card_type_classification():
    assert classify_card_type("孟潔 01/05 唇印親簽卡") == LIP_PRINT
    assert classify_card_type("高佳彬 8/10 新人親簽卡 (普通隊服簽)") == AUTOGRAPH
    assert classify_card_type("若潼 女僕拉鍊 Patch 1/1 金簽") == "PATCH_MEMORABILIA"
    assert classify_card_type("廉世彬 夏日泳裝 SP 簽名卡") == "SPECIAL_INSERT"


def test_serial_number_extraction():
    r1 = extract_serial_number("孟潔 01/05 唇印親簽卡")
    assert r1 == {"serial_number": "01/05", "is_first_num": True, "is_last_num": False}

    r2 = extract_serial_number("高佳彬 8/10 簽名卡")
    assert r2 == {"serial_number": "8/10", "is_first_num": False, "is_last_num": False}

    r3 = extract_serial_number("若潼 1/1 金簽")
    assert r3 == {"serial_number": "1/1", "is_first_num": True, "is_last_num": True}

    r4 = extract_serial_number("廉世彬 泳裝 SP 簽名卡 限量 10/10 (尾號)")
    assert r4 == {"serial_number": "10/10", "is_first_num": False, "is_last_num": True}

    assert extract_serial_number("沒有編號的商品標題") is None


def test_bundle_listing_detection():
    # 3 位以上不同成員同時出現在標題，視為整套合售，不能歸戶成任何單一成員的單卡價格
    bundle_title = "藍藍 若潼 孟潔 凱伊 陳伊 心璇 怡珊 Rakuten Girls 樂天女孩全味全龍啦啦隊限量性感比基尼卡"
    assert len(all_matched_members(bundle_title)) >= 3
    # 一般單卡標題只會比對到 1 位成員
    assert all_matched_members("孟潔 01/05 唇印親簽卡") == ["孟潔"]


if __name__ == "__main__":
    test_member_alias_matching()
    test_card_type_classification()
    test_serial_number_extraction()
    test_bundle_listing_detection()
    print("全部單元測試通過。")
