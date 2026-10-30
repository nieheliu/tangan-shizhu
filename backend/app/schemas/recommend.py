"""推荐接口的请求和响应。营养数字由后端填写。"""

from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    meal_type: str | None = Field(default=None, max_length=16)
    only_inventory: bool = False
    exclude_ids: list[int] = Field(default_factory=list)


class RecommendItem(BaseModel):
    recipe_id: int
    name: str
    score: int
    reason: str
    citation_ids: list[str]
    missing_foods: list[str]
    kcal: float | None
    carb_g: float | None
    protein_g: float | None
    fat_g: float | None
    fiber_g: float | None
    sodium_mg: float | None
    oil_estimated: bool
    main_staple_gi: float | None
    gi_band: str | None
    gi_band_label: str | None
    gi_band_source: str
    gl_estimate: float | None
    gl_is_approximate: bool


class RejectReason(BaseModel):
    rule_id: str
    message: str
    source: str


class RejectedRecipe(BaseModel):
    recipe_id: int
    name: str
    reasons: list[RejectReason]


class RecommendResponse(BaseModel):
    graph: str
    rag: str
    blocked: bool
    block_message: str | None
    strict: list[RecommendItem]
    relaxed: list[RecommendItem]
    rejected: list[RejectedRecipe]
