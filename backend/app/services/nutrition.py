"""身高体重换算。

热量用《中国居民膳食指南》里的简化估算：理想体重（千克）= 身高（厘米）− 105，
再乘每公斤热量系数。这不是临床营养处方。系数和 BMI 分界在核对指南前为「待核对」。
空腹血糖和糖化血红蛋白不参与计算。
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from app.core.config import get_settings

MIN_AGE = 18
KCAL_SOURCE = "待核对"
# 待核对：消瘦 < 18.5，超重或肥胖 >= 24。只用来选热量系数，不是诊断标准。
BMI_UNDER = Decimal("18.5")
BMI_OVER = Decimal(24)
# 待核对：每公斤理想体重的千卡，范围限制在 20～35。列顺序为消瘦、中间、超重。
_KCAL_PER_KG: dict[str, tuple[int, int, int]] = {
    "轻": (30, 25, 20),
    "中": (35, 30, 25),
    "重": (35, 35, 30),
}


@dataclass(frozen=True)
class KcalEstimate:
    ideal_weight_kg: Decimal
    kcal_per_kg: int
    suggested_kcal: int
    source: str


def current_year() -> int:
    zone = ZoneInfo(get_settings().app_timezone)
    return datetime.now(zone).year


def age_in_year(birth_year: int, year: int) -> int:
    return year - birth_year


def is_adult(birth_year: int, year: int) -> bool:
    return age_in_year(birth_year, year) >= MIN_AGE


def body_mass_index(height_cm: Decimal, weight_kg: Decimal) -> Decimal:
    height_m = height_cm / Decimal(100)
    return weight_kg / (height_m * height_m)


def kcal_per_kg(activity_level: str, bmi: Decimal) -> int | None:
    band = _KCAL_PER_KG.get(activity_level)
    if band is None:
        return None
    if bmi < BMI_UNDER:
        return band[0]
    if bmi < BMI_OVER:
        return band[1]
    return band[2]


def suggested_daily_kcal(
    height_cm: Decimal | None,
    weight_kg: Decimal | None,
    activity_level: str | None,
) -> KcalEstimate | None:
    if height_cm is None or weight_kg is None or not activity_level:
        return None
    ideal = height_cm - Decimal(105)
    if ideal <= 0:
        return None
    factor = kcal_per_kg(activity_level, body_mass_index(height_cm, weight_kg))
    if factor is None:
        return None
    kcal = (ideal * Decimal(factor)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return KcalEstimate(
        ideal_weight_kg=ideal,
        kcal_per_kg=factor,
        suggested_kcal=int(kcal),
        source=KCAL_SOURCE,
    )
