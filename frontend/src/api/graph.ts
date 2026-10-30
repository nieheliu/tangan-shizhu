import http from "./http";

export interface GraphNode {
  id: string;
  name: string;
  label: string;
  pg_id: number | null;
}

export interface GraphLink {
  source: string;
  target: string;
  relation: string;
  reason: string | null;
  citation: string | null;
}

export interface Neighborhood {
  graph: string;
  center: GraphNode | null;
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface FoodFacts {
  pg_id: number;
  name: string;
  category: string | null;
  per_g: number | null;
  kcal: number | null;
  carb_g: number | null;
  protein_g: number | null;
  fat_g: number | null;
  fiber_g: number | null;
  sodium_mg: number | null;
  gi: number | null;
  gi_source: string;
  nutrient_source: string;
}

export function fetchNeighbors(name: string, depth: number) {
  return http.get<Neighborhood>("/api/v1/graph/neighbors", { params: { name, depth } });
}

export function fetchFoodFacts(pgId: number) {
  return http.get<FoodFacts>(`/api/v1/graph/foods/${pgId}`);
}
