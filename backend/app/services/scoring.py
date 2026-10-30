"""推荐排序。这些整数只用于排序，不是医学剂量。"""

INVENTORY_HIT_PER_FOOD = 2
EXPIRING_BONUS_PER_FOOD = 3
GRAPH_RECOMMEND_PER_RELATION = 2
MISSING_PENALTY_PER_FOOD = 1
RESULT_LIMIT = 5
STRICT_MINIMUM = 3


def recipe_score(
    *,
    inventory_hits: int,
    expiring_hits: int,
    graph_relations: int,
    missing_foods: int,
    rule_delta: int,
) -> int:
    return (
        inventory_hits * INVENTORY_HIT_PER_FOOD
        + expiring_hits * EXPIRING_BONUS_PER_FOOD
        + graph_relations * GRAPH_RECOMMEND_PER_RELATION
        - missing_foods * MISSING_PENALTY_PER_FOOD
        + rule_delta
    )
