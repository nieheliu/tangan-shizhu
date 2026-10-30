import http from "./http";

export interface FoodOption {
  id: number;
  name: string;
  category: string | null;
  units: string[];
}

export function searchFoods(keyword: string) {
  return http.get<FoodOption[]>("/api/v1/foods/search", { params: { q: keyword } });
}
