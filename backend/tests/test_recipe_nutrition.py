from decimal import Decimal

from app.rules.engine import GI_HIGH_MIN as RULE_GI_HIGH_MIN
from app.services.recipe_nutrition import (
    GI_BAND_SOURCE,
    GI_HIGH_MIN,
    GI_LOW_MAX,
    IngredientLine,
    OilNutrients,
    calculate_recipe_nutrition,
    clear_recipe_nutrition_cache,
    gi_band,
    is_cooking_oil,
    load_cooking_oil,
)


def _line(
    food_id: int,
    name: str,
    amount_g: str,
    *,
    is_main: bool = False,
    is_oil: bool = False,
    kcal: str | None = "100",
    carb_g: str | None = "10",
    protein_g: str | None = "5",
    fat_g: str | None = "2",
    fiber_g: str | None = "1",
    sodium_mg: str | None = "10",
    gi: str | None = None,
    gi_source: str | None = None,
    per_g: str = "100",
) -> IngredientLine:
    return IngredientLine(
        food_id=food_id,
        name=name,
        amount_g=Decimal(amount_g),
        per_g=Decimal(per_g),
        is_main=is_main,
        is_oil=is_oil,
        kcal=None if kcal is None else Decimal(kcal),
        carb_g=None if carb_g is None else Decimal(carb_g),
        protein_g=None if protein_g is None else Decimal(protein_g),
        fat_g=None if fat_g is None else Decimal(fat_g),
        fiber_g=None if fiber_g is None else Decimal(fiber_g),
        sodium_mg=None if sodium_mg is None else Decimal(sodium_mg),
        gi=None if gi is None else Decimal(gi),
        gi_source=gi_source,
    )


def test_listed_oil_is_used_and_default_oil_is_not_added() -> None:
    # 燕麦 100 克：热量 200、碳水 50、蛋白质 10、脂肪 4、纤维 6、钠 20。
    # 花生油 10 克：热量 90、碳水 0、蛋白质 0、脂肪 10、纤维 0、钠 0。
    # 合计后除以 2 份：145、25、5、7、3、10。
    # 主食碳水每份 25，GL = 55 * 25 / 100 = 13.75。
    oats = _line(
        1,
        "燕麦",
        "100",
        is_main=True,
        kcal="200",
        carb_g="50",
        protein_g="10",
        fat_g="4",
        fiber_g="6",
        sodium_mg="20",
        gi="55",
        gi_source="测试出处",
    )
    oil = _line(
        2,
        "花生油",
        "10",
        is_oil=True,
        kcal="900",
        carb_g="0",
        protein_g="0",
        fat_g="100",
        fiber_g="0",
        sodium_mg="0",
    )
    result = calculate_recipe_nutrition(
        [oats, oil],
        servings=Decimal(2),
        cooking_method="炒",
        oil_table={"炒": (Decimal(15), "待核对")},
        default_oil=OilNutrients(per_g=Decimal(100), kcal=Decimal(900), fat_g=Decimal(100)),
    )
    assert result.kcal == Decimal("145.00")
    assert result.carb_g == Decimal("25.00")
    assert result.protein_g == Decimal("5.00")
    assert result.fat_g == Decimal("7.00")
    assert result.fiber_g == Decimal("3.00")
    assert result.sodium_mg == Decimal("10.00")
    assert result.nutrient_complete.kcal
    assert result.oil_estimated is False
    assert result.oil_grams is None
    assert result.oil_source is None
    assert result.main_staple_food_id == 1
    assert result.main_staple_name == "燕麦"
    assert result.main_staple_gi == Decimal(55)
    assert result.gi_source == "测试出处"
    assert result.gi_band == "low"
    assert result.gi_band_label == "低"
    assert result.gi_band_source == GI_BAND_SOURCE
    assert result.gl_estimate == Decimal("13.75")
    assert result.gl_is_approximate is True


def test_default_oil_grams_are_added_to_energy_and_fat_only() -> None:
    # 燕麦整份热量 200、脂肪 4、碳水 50。默认油 8 克：热量 72、脂肪 8。
    # 两份后：热量 136、脂肪 6、碳水 25。纤维和钠不加默认油。
    # 主食碳水每份 25，GL = 55 * 25 / 100 = 13.75。
    oats = _line(
        1,
        "燕麦",
        "100",
        is_main=True,
        kcal="200",
        carb_g="50",
        protein_g="10",
        fat_g="4",
        fiber_g="6",
        sodium_mg="20",
        gi="55",
        gi_source="测试出处",
    )
    result = calculate_recipe_nutrition(
        [oats],
        servings=Decimal(2),
        cooking_method="炒",
        oil_table={"炒": (Decimal(8), "待核对")},
        default_oil=OilNutrients(per_g=Decimal(100), kcal=Decimal(900), fat_g=Decimal(100)),
    )
    assert result.kcal == Decimal("136.00")
    assert result.fat_g == Decimal("6.00")
    assert result.carb_g == Decimal("25.00")
    assert result.protein_g == Decimal("5.00")
    assert result.fiber_g == Decimal("3.00")
    assert result.sodium_mg == Decimal("10.00")
    assert result.oil_estimated is True
    assert result.oil_grams == Decimal(8)
    assert result.oil_source == "待核对"
    assert result.gl_estimate == Decimal("13.75")
    assert result.gl_is_approximate is True


def test_blank_oil_grams_do_not_invent_an_amount() -> None:
    oats = _line(1, "燕麦", "100", is_main=True, kcal="200", fat_g="4", gi="55")
    result = calculate_recipe_nutrition(
        [oats],
        cooking_method="炒",
        oil_table={"炒": (None, "待核对")},
        default_oil=OilNutrients(per_g=Decimal(100), kcal=Decimal(900), fat_g=Decimal(100)),
    )
    assert result.kcal == Decimal("200.00")
    assert result.fat_g == Decimal("4.00")
    assert result.oil_estimated is False
    assert result.oil_grams is None
    assert result.oil_source == "待核对"


def test_current_oil_table_is_blank_for_every_method() -> None:
    table = load_cooking_oil()
    assert table
    assert all(grams is None and source == "待核对" for grams, source in table.values())
    oats = _line(1, "燕麦", "40", is_main=True, kcal="367", fat_g="6.7")
    result = calculate_recipe_nutrition(
        [oats],
        cooking_method="炒",
        default_oil=OilNutrients(per_g=Decimal(100), kcal=Decimal(899), fat_g=Decimal("99.9")),
    )
    assert result.kcal == Decimal("146.80")
    assert result.fat_g == Decimal("2.68")
    assert result.oil_grams is None
    assert result.oil_estimated is False
    assert result.oil_source == "待核对"


def test_missing_nutrient_makes_the_column_empty() -> None:
    food = _line(1, "燕麦", "100", kcal="200", fiber_g=None, sodium_mg="0")
    result = calculate_recipe_nutrition([food], oil_table={})
    assert result.kcal == Decimal("200.00")
    assert result.fiber_g is None
    assert result.sodium_mg == Decimal("0.00")
    assert result.nutrient_complete.kcal is True
    assert result.nutrient_complete.fiber_g is False


def test_missing_oil_nutrients_do_not_invent_energy() -> None:
    oats = _line(1, "燕麦", "100", kcal="200", fat_g="4")
    result = calculate_recipe_nutrition(
        [oats],
        cooking_method="炒",
        oil_table={"炒": (Decimal(8), "待核对")},
        default_oil=None,
    )
    assert result.kcal is None
    assert result.fat_g is None
    assert result.carb_g == Decimal("10.00")
    assert result.nutrient_complete.kcal is False
    assert result.nutrient_complete.fat_g is False
    assert result.oil_estimated is True
    assert result.oil_grams == Decimal(8)


def test_main_staple_is_the_largest_amount_with_gi() -> None:
    missing = _line(1, "无GI", "200", is_main=True, gi=None, carb_g="80")
    smaller = _line(2, "小份", "80", is_main=True, gi="70", carb_g="40", gi_source="小")
    larger = _line(3, "大份", "100", is_main=True, gi="50", carb_g="20", gi_source="大")
    result = calculate_recipe_nutrition(
        [missing, smaller, larger],
        oil_table={},
    )
    assert result.main_staple_food_id == 3
    assert result.main_staple_name == "大份"
    assert result.main_staple_gi == Decimal(50)
    assert result.gi_source == "大"
    assert result.gl_estimate == Decimal("10.00")


def test_equal_amounts_pick_the_smaller_food_id() -> None:
    later = _line(5, "后", "100", is_main=True, gi="80", carb_g="10")
    earlier = _line(2, "先", "100", is_main=True, gi="40", carb_g="10")
    result = calculate_recipe_nutrition([later, earlier], oil_table={})
    assert result.main_staple_food_id == 2
    assert result.main_staple_gi == Decimal(40)


def test_missing_main_gi_is_not_low_and_gl_stays_empty() -> None:
    food = _line(1, "红薯", "150", is_main=True, gi=None, carb_g="30")
    result = calculate_recipe_nutrition([food], oil_table={})
    assert result.main_staple_gi is None
    assert result.main_staple_food_id is None
    assert result.gi_band is None
    assert result.gi_band_label is None
    assert result.gi_band_source == "待核对"
    assert result.gl_estimate is None
    assert result.gl_is_approximate is True


def test_gi_bands_use_the_same_bounds_as_the_rules() -> None:
    assert GI_LOW_MAX == Decimal(55)
    assert GI_HIGH_MIN == Decimal(RULE_GI_HIGH_MIN)
    assert gi_band(Decimal(55)) == ("low", "低")
    assert gi_band(Decimal("55.1")) == ("medium", "中")
    assert gi_band(Decimal("69.9")) == ("medium", "中")
    assert gi_band(Decimal(70)) == ("high", "高")
    assert gi_band(None) == (None, None)


def test_gl_rounds_half_up_and_empty_carb_has_no_gl() -> None:
    # 55 * 10.01 / 100 = 5.5055，保留两位为 5.51。
    measured = _line(1, "燕麦", "100", is_main=True, gi="55", carb_g="10.01")
    rounded = calculate_recipe_nutrition([measured], oil_table={})
    assert rounded.gl_estimate == Decimal("5.51")
    empty = _line(1, "燕麦", "100", is_main=True, gi="55", carb_g=None)
    assert calculate_recipe_nutrition([empty], oil_table={}).gl_estimate is None


def test_per_g_and_blank_servings() -> None:
    # 50 克相对每 50 克的 80 千卡，贡献就是 80。份数空按 1。
    food = _line(1, "燕麦", "50", per_g="50", kcal="80")
    result = calculate_recipe_nutrition([food], servings=None, oil_table={})
    assert result.kcal == Decimal("80.00")


def test_cache_keeps_the_first_result_until_cleared() -> None:
    clear_recipe_nutrition_cache()
    first_food = _line(1, "燕麦", "100", kcal="200")
    second_food = _line(1, "燕麦", "100", kcal="400")
    try:
        first = calculate_recipe_nutrition([first_food], oil_table={}, recipe_id=904)
        second = calculate_recipe_nutrition([second_food], oil_table={}, recipe_id=904)
        assert second is first
        assert second.kcal == Decimal("200.00")
        clear_recipe_nutrition_cache()
        third = calculate_recipe_nutrition([second_food], oil_table={}, recipe_id=904)
        assert third.kcal == Decimal("400.00")
    finally:
        clear_recipe_nutrition_cache()


def test_cooking_oil_category_does_not_match_vegetables() -> None:
    assert is_cooking_oil("油脂")
    assert is_cooking_oil("植物油-植物油")
    assert is_cooking_oil("动物油脂类-动物油脂")
    assert not is_cooking_oil("蔬菜")
    assert not is_cooking_oil("蔬菜类及其制品-嫩茎叶花菜类")
    assert not is_cooking_oil(None)
