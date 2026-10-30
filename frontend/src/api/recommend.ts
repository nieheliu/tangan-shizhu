import type { NutritionFacts } from "./nutrition";
import http from "./http";

export interface RecommendRequest {
  meal_type: string | null;
  only_inventory: boolean;
  exclude_ids: number[];
}

export interface RecommendItem extends NutritionFacts {
  recipe_id: number;
  name: string;
  score: number;
  reason: string;
  citation_ids: string[];
  missing_foods: string[];
  held_foods: string[];
}

export interface RejectReason {
  rule_id: string;
  message: string;
  source: string;
}

export interface RejectedRecipe {
  recipe_id: number;
  name: string;
  reasons: RejectReason[];
}

export interface RecommendResponse {
  graph: string;
  rag: string;
  blocked: boolean;
  block_message: string | null;
  strict: RecommendItem[];
  relaxed: RecommendItem[];
  rejected: RejectedRecipe[];
}

export function fetchRecommend(body: RecommendRequest) {
  return http.post<RecommendResponse>("/api/v1/recommend", body, { timeout: 70000 });
}
