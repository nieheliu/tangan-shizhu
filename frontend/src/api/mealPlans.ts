import http from "./http";

export interface MealPlanView {
  id: number;
  date: string;
  meal_type: string;
  recipe_id: number;
  already_added: boolean;
}

export function addMealPlan(recipeId: number, mealType: string) {
  return http.post<MealPlanView>("/api/v1/meal-plans", {
    recipe_id: recipeId,
    meal_type: mealType,
  });
}
