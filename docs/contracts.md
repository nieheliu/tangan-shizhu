# 共享约定

阶段 3 起，食谱营养、规则上下文、排序权重和 GI 分级都用这份字段名。要改名字或权重，同时改本文和对应测试。

营养数字只从 PostgreSQL 的 `foods` 计算。模型不返回热量、GI 或 GL。Neo4j 节点上不写这些数字。

血糖和糖化血红蛋白不出现在规则上下文里，也不参与排序。

## 1. 食谱营养

按一份计算。食材营养先按克数相加，再除以 `recipes.servings`（空则按 1）。

食材克数用 `recipe_ingredients.amount_g`。食物每 `foods.per_g` 克的含量（成分表为 100）换算成这份食谱的克数：

```
食材贡献 = amount_g / per_g * 该列数值
食谱每份 = 全部食材贡献之和 / servings
```

某一列在用到的食材上只要有一条是空（包括成分表里的 Tr、横线、空白），这一列整份结果就是空，不用 0 填。`nutrient_complete` 标出哪些列是完整相加的。

| 字段 | 含义 | 单位 |
|---|---|---|
| `kcal` | 能量 | 千卡 |
| `carb_g` | 碳水化合物 | 克 |
| `protein_g` | 蛋白质 | 克 |
| `fat_g` | 脂肪 | 克 |
| `fiber_g` | 膳食纤维 | 克 |
| `sodium_mg` | 钠 | 毫克 |

没有单独的添加糖列，也没有钾列。不要临时加这两项。

烹调油：食谱食材里已经有油时，用食谱克数，`oil_estimated` 为 false。没有油时，按 `cooking_oil.csv` 里该 `cooking_method` 的克数补一条油，计入 `kcal` 和 `fat_g`，`oil_estimated` 为 true。该表克数仍是空的，来源是 `待核对`；克数为空就不补油，并在结果里带 `oil_source: "待核对"`。

## 2. 主食 GI 与粗估 GL

主食是 `recipe_ingredients.is_main = true` 的食材。多条主食时，取其中 GI 不为空且 `amount_g` 最大的一条。没有主食，或主食没有 GI 时，`main_staple_gi` 为空，不当成 0，也不当成低 GI。

| 字段 | 含义 |
|---|---|
| `main_staple_food_id` | 主食的 `foods.id`，没有则为空 |
| `main_staple_name` | 主食名称 |
| `main_staple_gi` | 该食物的 `foods.gi` |
| `gi_source` | 该食物的 `foods.gi_source` |
| `gi_band` | `low` / `medium` / `high`，GI 为空时为空 |
| `gi_band_label` | `低` / `中` / `高`，GI 为空时为空 |
| `gi_band_source` | 分界出处。未对照指南前固定为 `待核对` |
| `gl_estimate` | 只按主食粗估，见下式。GI 或主食碳水为空时为空 |
| `gl_is_approximate` | 固定为 true |

分界（工作常量，不是已核对的临床标准）：

| 分级 | 条件 | 常量 |
|---|---|---|
| 低 | `main_staple_gi <= 55` | `gi_low_max = 55` |
| 中 | 大于 55 且小于 70 | |
| 高 | `main_staple_gi >= 70` | `gi_high_min = 70` |

`source: "待核对"`。这是常见 GI 分界的写法，尚未对照《成人糖尿病食养指南（2023 年版）》页码。界面在 `gi_band_source` 为 `待核对` 时要标出“待核对”。规则 YAML 里的 70 必须与 `gi_high_min` 相同，不能再写另一套阈值。

粗估 GL 只覆盖主食的碳水，不是整盘菜按克加权：

```
gl_estimate = main_staple_gi * main_staple_carb_g / 100
```

`main_staple_carb_g` 是这份食谱里该主食的碳水克数（已按 `amount_g / per_g` 换算，再除以份数）。

## 3. 规则上下文

`when` 只用下面这些名字。`simpleeval` 不接触档案里的空腹血糖和糖化血红蛋白。

| 变量 | 类型 | 来源 |
|---|---|---|
| `kcal` | 数或空 | 第 1 节 |
| `carb_g` | 数或空 | 第 1 节 |
| `protein_g` | 数或空 | 第 1 节 |
| `fat_g` | 数或空 | 第 1 节 |
| `fiber_g` | 数或空 | 第 1 节 |
| `sodium_mg` | 数或空 | 第 1 节 |
| `main_staple_gi` | 数或空 | 第 2 节 |
| `main_staple_name` | 字符串或空 | 第 2 节 |
| `food_ids` | 整数列表 | 食谱食材 |
| `food_names` | 字符串列表 | 食谱食材名称 |
| `allergen_hit` | 布尔 | 食材名或别名与档案过敏原有交集 |
| `dislike_count` | 整数 | 食材名或别名与忌口的交集条数 |
| `diseases` | 字符串列表 | 档案疾病，推荐逻辑只认 `2型糖尿病` |

空值参与比较时，这条规则不命中。不要把空 GI 当成 0。

过敏原：`allergen_hit` 为 true 时 `reject`，整道菜排除。忌口：只减分，不排除。`dislike_delta = dislike_count * dislike_delta_per_food`。

每条命中的规则返回 `rule_id`、`message`、`source`。`type` 为 `reject`、`warn` 或 `score`。

## 4. 排序权重

这些是排序用的整数，不是医学剂量。`reject` 在打分之前执行，被排除的菜不进入下面的公式。

```
最终分 = 库存命中分 + 临期分 + 图谱推荐分 - 缺失食材分 + 规则 delta
```

| 常量 | 值 | 算法 |
|---|---|---|
| `inventory_hit_per_food` | 2 | 未过期库存里有的食材，每种加 2 |
| `expiring_bonus_per_food` | 3 | 其中到期前 2 天（`Asia/Shanghai`）的，每种再加 3 |
| `graph_recommend_per_relation` | 2 | 食材命中 `(Disease)-[:RECOMMEND]->(Food)` 的条数，每条加 2 |
| `missing_penalty_per_food` | 1 | 食谱需要但库存没有的食材，每种减 1 |
| `dislike_delta_per_food` | -1 | 每种忌口命中减 1，并入规则 delta |

已过期库存不算命中。Neo4j 不可用时图谱推荐分为 0，响应里 `graph` 为 `down`。Chroma 不可用时推荐继续，`rag` 为 `down`。规则引擎不可用时接口报错，不用 0 分代替。

`only_inventory=true` 且通过规则的菜不足 3 道时，严格结果和放宽库存后的结果分两个列表，不混在一起。

## 5. 推荐响应里由后端填写的字段

模型只返回 `recipe_id`、`reason`、`citation_ids`。下面这些由后端写入，模型给了也丢掉：

`kcal`、`carb_g`、`protein_g`、`fat_g`、`fiber_g`、`sodium_mg`、`oil_estimated`、`main_staple_gi`、`gi_band`、`gi_band_label`、`gi_band_source`、`gl_estimate`、`gl_is_approximate`、`score`。

`citation_ids` 必须来自本次检索。没有检索片段时，理由里不写指南条号。
