"""规则引擎。when 用 simpleeval，不使用 Python eval。

上下文只有 docs/contracts.md 列出的名字。空腹血糖和糖化血红蛋白不会放进去。
空值参与比较时，这条规则不命中，不把空 GI 当成 0。
"""

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml
from simpleeval import InvalidExpression, NameNotDefined, SimpleEval

GI_HIGH_MIN = 70
DISLIKE_DELTA_PER_FOOD = -1
_RULES_DIR = Path(__file__).resolve().parent
_ALLOWED = (
    "kcal",
    "carb_g",
    "protein_g",
    "fat_g",
    "fiber_g",
    "sodium_mg",
    "main_staple_gi",
    "main_staple_name",
    "food_ids",
    "food_names",
    "allergen_hit",
    "dislike_count",
    "diseases",
)
_TYPES = frozenset({"reject", "warn", "score", "block"})


class RulesError(Exception):
    """规则文件或表达式无法使用。调用方应返回错误，不要当成 0 分。"""


@dataclass(frozen=True)
class Rule:
    rule_id: str
    type: str
    when: str
    message: str
    source: str
    delta: int
    per: str | None
    disease: str | None
    filename: str


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    message: str
    source: str
    type: str
    delta: int


@dataclass(frozen=True)
class RuleOutcome:
    rejected: bool
    blocked: bool
    block_message: str | None
    hits: tuple[RuleHit, ...]
    delta: int


def recipe_names(context: dict[str, object]) -> dict[str, object]:
    names = {key: _coerce(context.get(key)) for key in _ALLOWED}
    if names["allergen_hit"] is None:
        names["allergen_hit"] = False
    if names["dislike_count"] is None:
        names["dislike_count"] = 0
    if not isinstance(names["diseases"], list):
        names["diseases"] = []
    if not isinstance(names["food_ids"], list):
        names["food_ids"] = []
    if not isinstance(names["food_names"], list):
        names["food_names"] = []
    if names["main_staple_name"] is None:
        names["main_staple_name"] = ""
    return names


def evaluate(
    context: dict[str, object] | None = None,
    *,
    age: int | None = None,
    user_text: str = "",
) -> RuleOutcome:
    names = recipe_names(context or {})
    safety_names = {**names, "minor": age is not None and age < 18}
    blocks = [
        hit
        for rule in load_rules()
        if rule.filename == "safety.yaml"
        if (hit := _match(rule, safety_names, user_text)) is not None
    ]
    if blocks:
        return RuleOutcome(
            rejected=True,
            blocked=True,
            block_message=blocks[0].message,
            hits=tuple(blocks),
            delta=0,
        )

    hits: list[RuleHit] = []
    for rule in load_rules():
        if rule.filename == "safety.yaml" or not _disease_applies(rule, names):
            continue
        hit = _match(rule, names, "")
        if hit is not None:
            hits.append(hit)
    rejected = any(hit.type == "reject" for hit in hits)
    delta = 0 if rejected else sum(hit.delta for hit in hits if hit.type == "score")
    return RuleOutcome(
        rejected=rejected,
        blocked=False,
        block_message=None,
        hits=tuple(hits),
        delta=delta,
    )


def reload_rules() -> None:
    load_rules.cache_clear()


@lru_cache
def load_rules() -> tuple[Rule, ...]:
    rules: list[Rule] = []
    for filename in ("common.yaml", "diabetes.yaml", "safety.yaml"):
        path = _RULES_DIR / filename
        if not path.is_file():
            raise RulesError(f"缺少规则文件 {filename}")
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict) or not isinstance(loaded.get("rules"), list):
            raise RulesError(f"{filename} 没有 rules 列表")
        disease = loaded.get("disease")
        disease_name = disease if isinstance(disease, str) and disease else None
        for raw in loaded["rules"]:
            rules.append(_parse_rule(raw, disease_name, filename))
    return tuple(rules)


def _parse_rule(raw: object, disease: str | None, filename: str) -> Rule:
    if not isinstance(raw, dict):
        raise RulesError(f"{filename} 里有一条规则不是映射")
    rule_id = str(raw.get("id") or "").strip()
    rule_type = str(raw.get("type") or "").strip()
    when = str(raw.get("when") or "").strip()
    message = str(raw.get("message") or "").strip()
    source = str(raw.get("source") or "").strip()
    if not rule_id or not when or not message or not source:
        raise RulesError(f"{filename} 的规则缺少 id、when、message 或 source")
    if rule_type not in _TYPES:
        raise RulesError(f"{rule_id} 的 type 无法识别")
    delta = int(raw.get("delta") or 0)
    per = raw.get("per")
    per_name = str(per) if isinstance(per, str) and per else None
    if rule_id == "COMMON-002" and delta != DISLIKE_DELTA_PER_FOOD:
        raise RulesError("忌口每项减分必须与约定的 dislike_delta_per_food 一致")
    if rule_id == "DM-001" and when != f"main_staple_gi >= {GI_HIGH_MIN}":
        raise RulesError("高 GI 阈值必须与 gi_high_min 一致")
    return Rule(
        rule_id=rule_id,
        type=rule_type,
        when=when,
        message=message,
        source=source,
        delta=delta,
        per=per_name,
        disease=disease,
        filename=filename,
    )


def _match(rule: Rule, names: dict[str, object], user_text: str) -> RuleHit | None:
    if not _condition(rule.when, names, user_text, rule.filename == "safety.yaml"):
        return None
    delta = _delta(rule, names) if rule.type == "score" else 0
    return RuleHit(
        rule_id=rule.rule_id,
        message=rule.message,
        source=rule.source,
        type=rule.type,
        delta=delta,
    )


def _condition(
    expression: str,
    names: dict[str, object],
    user_text: str,
    safety: bool,
) -> bool:
    functions: dict[str, object] = {"mentions": _mentions}
    if safety:
        functions["text_has"] = lambda marker: marker in user_text
    evaluator = SimpleEval(names=names, functions=functions)
    try:
        return bool(evaluator.eval(expression))
    except NameNotDefined:
        return False
    except TypeError:
        return False
    except InvalidExpression as exc:
        raise RulesError(f"规则表达式无法计算：{expression}") from exc


def _delta(rule: Rule, names: dict[str, object]) -> int:
    if rule.per is None:
        return rule.delta
    count = names.get(rule.per) or 0
    return rule.delta * int(count)


def _disease_applies(rule: Rule, names: dict[str, object]) -> bool:
    if rule.disease is None:
        return True
    diseases = names.get("diseases")
    return isinstance(diseases, list) and rule.disease in diseases


def _mentions(items: object, marker: str) -> bool:
    if not isinstance(items, list):
        return False
    return any(marker in str(item) for item in items)


def _coerce(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    return value
