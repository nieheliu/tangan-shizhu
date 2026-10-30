import http from "./http";

export interface ShoppingItem {
  id: number;
  food_id: number;
  food_name: string;
  category: string;
  amount_g: number;
  quantity: number;
  unit: string;
  checked: boolean;
}

export interface ShoppingGroup {
  category: string;
  items: ShoppingItem[];
}

export interface ExcludedFood {
  food_id: number;
  food_name: string;
  reason: string;
}

export interface ShoppingList {
  id: number;
  start: string;
  end: string;
  groups: ShoppingGroup[];
  excluded: ExcludedFood[];
}

export interface InventoryAdded {
  id: number;
  food_id: number;
  food_name: string;
  quantity: number;
  unit: string;
  grams: number | null;
}

export interface TransferResult {
  added: InventoryAdded[];
  skipped: { food_name: string; detail: string }[];
  shopping: ShoppingList;
}

export function generateShopping(scope: "daily" | "weekly", day: string) {
  return http.post<ShoppingList>("/api/v1/shopping/generate", { scope, date: day });
}

export function addShoppingItem(listId: number, foodId: number, amountG: number) {
  return http.post<ShoppingList>(`/api/v1/shopping/${listId}/items`, {
    food_id: foodId,
    amount_g: amountG,
  });
}

export function updateShoppingItem(itemId: number, checked: boolean) {
  return http.patch<ShoppingItem>(`/api/v1/shopping/items/${itemId}`, { checked });
}

export function moveShoppingToInventory(listId: number) {
  return http.post<TransferResult>(`/api/v1/shopping/${listId}/to-inventory`);
}
