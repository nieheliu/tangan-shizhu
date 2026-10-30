import { flushPromises, mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import { addMealPlan } from "../src/api/mealPlans";
import { fetchRecipe, type RecipeDetail } from "../src/api/recipes";
import RecipeView from "../src/views/RecipeView.vue";

vi.mock("../src/api/recipes", () => ({
  fetchRecipe: vi.fn(),
}));

vi.mock("../src/api/mealPlans", () => ({
  addMealPlan: vi.fn(),
}));

const detail: RecipeDetail = {
  id: 3,
  name: "燕麦粥",
  cuisine: "家常",
  meal_types: ["早餐"],
  cooking_method: "煮",
  steps: "燕麦加水煮至软。",
  servings: 1,
  image_url: null,
  source: "待核对",
  ingredients: [{ food_id: 5, name: "燕麦", amount_g: 100, is_main: true }],
  graph: "down",
  links: [],
  kcal: 200,
  carb_g: 10,
  protein_g: 1,
  fat_g: 1,
  fiber_g: 0,
  sodium_mg: 0,
  oil_estimated: false,
  gi_band_label: "低",
  gi_band_source: "待核对",
  gl_estimate: 5,
  gl_is_approximate: true,
};

async function mountPage(path = "/recipe/3?meal=早餐") {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/recipe/:id", component: RecipeView }],
  });
  await router.push(path);
  const wrapper = mount(RecipeView, {
    global: { plugins: [ElementPlus, router] },
  });
  await flushPromises();
  return wrapper;
}

describe("recipe page", () => {
  beforeEach(() => {
    vi.mocked(fetchRecipe).mockReset();
    vi.mocked(addMealPlan).mockReset();
    vi.mocked(fetchRecipe).mockResolvedValue({ data: detail } as never);
  });

  it("shows ingredients, steps, approximate GL and a down graph", async () => {
    const wrapper = await mountPage();
    expect(wrapper.text()).toContain("燕麦粥");
    expect(wrapper.text()).toContain("燕麦加水煮至软。");
    expect(wrapper.text()).toContain("燕麦");
    expect(wrapper.text()).toContain("低（阈值待核对）");
    expect(wrapper.text()).toContain("粗估 5");
    expect(wrapper.text()).toContain("图谱暂时不可用");
    expect(wrapper.text()).toContain("来源：待核对");
  });

  it("adds the meal from the query", async () => {
    vi.mocked(addMealPlan).mockResolvedValue({
      data: { id: 1, date: "2026-10-30", meal_type: "早餐", recipe_id: 3, already_added: true },
    } as never);
    const wrapper = await mountPage();
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(addMealPlan).toHaveBeenCalledWith(3, "早餐");
  });

  it("shows an error when the recipe cannot be loaded", async () => {
    vi.mocked(fetchRecipe).mockRejectedValueOnce(new Error("missing"));
    const wrapper = await mountPage();
    expect(wrapper.text()).toContain("暂时读不到这道食谱");
    expect(wrapper.text()).toContain("重试");
  });
});
