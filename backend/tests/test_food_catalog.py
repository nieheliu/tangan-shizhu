from decimal import Decimal

from app.services.food_catalog import (
    composition_records,
    gi_records,
    normalize_food_name,
    parse_nutrient,
)


def test_parse_nutrient_keeps_trace_and_blank_empty() -> None:
    assert parse_nutrient("2.50") == Decimal("2.50")
    assert parse_nutrient("Tr") is None
    assert parse_nutrient("—") is None
    assert parse_nutrient("") is None
    assert parse_nutrient("不是数字") is None


def test_normalize_food_name_strips_marker_and_space() -> None:
    assert normalize_food_name(" *燕麦片 ") == "燕麦片"
    assert normalize_food_name("MM  巧克力") == "MM 巧克力"


def test_duplicate_composition_names_keep_food_code() -> None:
    rows = [
        {
            "foodCode": "1",
            "foodName": "奶油",
            "englishName": "",
            "category": "油脂",
            "energyKCal": "800",
            "CHO": "Tr",
            "protein": "1",
            "fat": "80",
            "dietaryFiber": "—",
            "Na": "10",
        },
        {
            "foodCode": "2",
            "foodName": "奶油",
            "englishName": "cream",
            "category": "油脂",
            "energyKCal": "700",
            "CHO": "2",
            "protein": "1",
            "fat": "70",
            "dietaryFiber": "0",
            "Na": "20",
        },
    ]
    records = composition_records(rows)
    assert [record.name for record in records] == ["奶油〔1〕", "奶油〔2〕"]
    assert records[0].carb_g is None
    assert records[1].alias == ["cream"]


def test_conflicting_gi_values_are_not_merged() -> None:
    groups = [
        {
            "foodGroup": "谷类",
            "list": [
                {"foodName": "大米粥", "GI": 69},
                {"foodName": "*大米粥", "GI": 80},
                {"foodName": "苹果", "GI": 36},
            ],
        }
    ]
    ready, conflicts = gi_records(groups)
    assert [record.name for record in ready] == ["苹果"]
    assert conflicts[0][0] == "大米粥"
