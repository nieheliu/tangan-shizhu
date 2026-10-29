import http from "./http";

export interface HealthResponse {
  status: string;
  components: Record<string, string>;
}

export function fetchHealth() {
  return http.get<HealthResponse>("/api/v1/health");
}
