"""Kiểm thử tính năng phân tầng TICKER và cơ chế chặn false positive Tier 2."""

from src.agent.entities import EntityRegistry


def test_ticker_tiering_detection():
    """Kiểm tra mã Tier 1 được nhận diện tự do, còn Tier 2 chỉ nhận diện khi là CBTT hoặc alias."""
    entities = [
        {
            "entity_id": "TICKER:HPG",
            "type": "TICKER",
            "code": "HPG",
            "canonical_name": "Công ty Cổ phần Tập đoàn Hòa Phát",
            "aliases": ["Hòa Phát", "Hoa Phat"],
            "attributes": {"tier": 1, "market_cap_bil": 85000.0, "is_active": True},
        },
        {
            "entity_id": "TICKER:CAN",
            "type": "TICKER",
            "code": "CAN",
            "canonical_name": "Công ty Cổ phần Đồ hộp Hạ Long",
            "aliases": ["Đồ hộp Hạ Long", "Do hop Ha Long"],
            "attributes": {"tier": 2, "market_cap_bil": 150.0, "is_active": True},
        },
    ]

    reg = EntityRegistry(entities)

    # 1. Tier 1 (HPG): mã trần xuất hiện ở đâu cũng được nhận diện
    res_hpg = reg.detect("Cổ phiếu HPG tăng trưởng mạnh mẽ trong quý 3")
    eids_hpg = [r["entity_id"] for r in res_hpg]
    assert "TICKER:HPG" in eids_hpg

    # 2. Tier 2 (CAN): mã 3 chữ cái trần xuất hiện trong câu KHÔNG được nhận diện (tránh từ tiếng Việt 'cần', 'can')
    res_can_bare = reg.detect("Thị trường chứng khoán CAN có những bước chuyển mình")
    eids_can_bare = [r["entity_id"] for r in res_can_bare]
    assert "TICKER:CAN" not in eids_can_bare

    # 3. Tier 2 (CAN): xuất hiện dưới dạng công bố thông tin đầu tiêu đề ("CAN: ...") ĐƯỢC nhận diện
    res_can_disclosure = reg.detect("CAN: Báo cáo tài chính quý 3 năm 2026")
    eids_can_disclosure = [r["entity_id"] for r in res_can_disclosure]
    assert "TICKER:CAN" in eids_can_disclosure

    # 4. Tier 2 (CAN): xuất hiện qua alias thương hiệu ĐƯỢC nhận diện
    res_can_alias = reg.detect("Lợi nhuận sau thuế của Đồ hộp Hạ Long tăng 15%")
    eids_can_alias = [r["entity_id"] for r in res_can_alias]
    assert "TICKER:CAN" in eids_can_alias
