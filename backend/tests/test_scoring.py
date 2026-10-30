"""排序公式。这些整数只用来比较食谱。"""

from app.services.scoring import recipe_score


def test_score_combines_inventory_graph_and_rules() -> None:
    assert (
        recipe_score(
            inventory_hits=2,
            expiring_hits=1,
            graph_relations=1,
            missing_foods=1,
            rule_delta=-1,
        )
        == 7
    )
