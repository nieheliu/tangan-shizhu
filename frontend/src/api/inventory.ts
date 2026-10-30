import http from "./http";

export interface InventoryItem {
  id: number;
  food_id: number;
  food_name: string;
  quantity: number;
  unit: string;
  grams: number | null;
  purchased_at: string | null;
  expires_at: string | null;
  status: string;
}

export interface InventoryPayload {
  food_id: number;
  quantity: number;
  unit: string;
  purchased_at: string | null;
  expires_at: string | null;
}

export function fetchInventory() {
  return http.get<InventoryItem[]>("/api/v1/inventory");
}

export function fetchReminders() {
  return http.get<InventoryItem[]>("/api/v1/inventory/reminders");
}

export function createInventory(payload: InventoryPayload) {
  return http.post<InventoryItem>("/api/v1/inventory", payload);
}

export function updateInventory(id: number, payload: InventoryPayload) {
  return http.put<InventoryItem>(`/api/v1/inventory/${id}`, payload);
}

export function deleteInventory(id: number) {
  return http.delete<{ ok: boolean }>(`/api/v1/inventory/${id}`);
}
