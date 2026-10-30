import { flushPromises, mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import { addMealPlan } from "../src/api/mealPlans";
import { fetchRecommend, type RecommendItem, type RecommendResponse } from "../src/api/recommend";
import RecommendView from "../src/views/RecommendView.vue";

vi.mock("../src/api/recommend", () => ({
  fetchRecommend: vi.fn(),
}));

vi.mock("../src/api/mealPlans", () => ({
  addMealPlan: vi.fn(),
}));

function item(id: number, name: string, extra: Partial<RecommendItem> = {}): RecommendItem {
  return {
    recipe_id: id,
    name,
    score: 2,
    reason: "推荐理由：含库存食材 燕麦；主食 GI 分级为低",
    citation_ids: ["guide:1:0"],
    missing_foods: [],
    held_foods: ["燕麦"],
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
    ...extra,
  };
}

function payload(extra: Partial<RecommendResponse> = {}): RecommendResponse {
  return {
    graph: "up",
    rag: "down",
    blocked: false,
    block_message: null,
    strict: [item(1, "燕麦粥")],
    relaxed: [],
    rejected: [],
    ...extra,
  };
}

async function mountPage() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/recommend", component: RecommendView },
      { path: "/recipe/:id", component: { template: "<div>detail</div>" } },
    ],
  });
  await router.push("/recommend");
  const wrapper = mount(RecommendView, {
    global: { plugins: [ElementPlus, router] },
  });
  await flushPromises();
  return wrapper;
}

describe("recommend page", () => {
  beforeEach(() => {
    vi.mocked(fetchRecommend).mockReset();
    vi.mocked(addMealPlan).mockReset();
  });

  it("shows nutrition from the response and keeps relaxed separate", async () => {
    vi.mocked(fetchRecommend).mockResolvedValue({
      data: payload({
        strict: [item(1, "燕麦粥")],
        relaxed: [item(2, "荞麦饭", { missing_foods: ["荞麦"], held_foods: [] })],
      }),
    } as never);
    const wrapper = await mountPage();
    expect(wrapper.text()).toContain("燕麦粥");
    expect(wrapper.text()).not.toContain("放宽后需购买");
    expect(wrapper.text()).toContain("低（阈值待核对）");
    expect(wrapper.text()).toContain("粗估 5");
    expect(wrapper.text()).toContain("库存已有 燕麦");
    expect(wrapper.text()).toContain("检索 down");
  });

  it("splits strict and relaxed results", async () => {
    vi.mocked(fetchRecommend).mockResolvedValue({
      data: payload({
        strict: [item(1, "燕麦粥")],
        relaxed: [item(2, "荞麦饭", { missing_foods: ["荞麦"], held_foods: [] })],
      }),
    } as never);
    const wrapper = await mountPage();
    await wrapper.get("input[type='checkbox']").setValue(true);
    await wrapper.get("button").trigger("click");
    await flushPromises();
    const text = wrapper.text();
    const strictAt = text.indexOf("严格结果");
    const relaxedAt = text.indexOf("放宽后需购买");
    expect(strictAt).toBeGreaterThan(-1);
    expect(relaxedAt).toBeGreaterThan(strictAt);
    expect(text.indexOf("燕麦粥")).toBeLessThan(relaxedAt);
    expect(text.indexOf("需购买 荞麦")).toBeGreaterThan(relaxedAt);
  });

  it("shows why a recipe was rejected", async () => {
    vi.mocked(fetchRecommend).mockResolvedValue({
      data: payload({
        rejected: [
          {
            recipe_id: 3,
            name: "白米饭",
            reasons: [
              { rule_id: "DM-001", message: "主食为高 GI 食物", source: "指南待核对" },
            ],
          },
        ],
      }),
    } as never);
    const wrapper = await mountPage();
    expect(wrapper.text()).toContain("为什么不推荐");
    const header = wrapper.find(".el-collapse-item__header");
    expect(header.exists()).toBe(true);
    await header.trigger("click");
    expect(wrapper.text()).toContain("DM-001");
    expect(wrapper.text()).toContain("白米饭");
    expect(wrapper.text()).toContain("指南待核对");
  });

  it("shows an error and can retry", async () => {
    vi.mocked(fetchRecommend)
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce({ data: payload() } as never);
    const wrapper = await mountPage();
    expect(wrapper.text()).toContain("暂时无法生成推荐");
    const retry = wrapper.findAll("button").find((button) => button.text() === "重试");
    expect(retry).toBeTruthy();
    await retry?.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("燕麦粥");
  });

  it("blocks the list when the profile must see a doctor", async () => {
    vi.mocked(fetchRecommend).mockResolvedValue({
      data: payload({
        blocked: true,
        block_message: "档案中有肾病相关情况，不生成个体化食谱，请就医或咨询医生、营养师。",
        strict: [],
      }),
    } as never);
    const wrapper = await mountPage();
    expect(wrapper.text()).toContain("请就医");
    expect(wrapper.text()).not.toContain("加入今日计划");
  });

  it("excludes the current recipes when asking for another batch", async () => {
    vi.mocked(fetchRecommend)
      .mockResolvedValueOnce({ data: payload() } as never)
      .mockResolvedValueOnce({ data: payload({ strict: [item(4, "小米粥")] }) } as never);
    const wrapper = await mountPage();
    const swap = wrapper.findAll("button").find((button) => button.text() === "换一批");
    await swap?.trigger("click");
    await flushPromises();
    expect(vi.mocked(fetchRecommend).mock.calls[1]?.[0]).toMatchObject({
      exclude_ids: [1],
      meal_type: "午餐",
    });
    expect(wrapper.text()).toContain("小米粥");
  });

  it("adds the shown meal to today's plan", async () => {
    vi.mocked(fetchRecommend).mockResolvedValue({ data: payload() } as never);
    vi.mocked(addMealPlan).mockResolvedValue({
      data: { id: 1, date: "2026-10-30", meal_type: "午餐", recipe_id: 1, already_added: false },
    } as never);
    const wrapper = await mountPage();
    const add = wrapper.findAll("button").find((button) => button.text() === "加入今日计划");
    await add?.trigger("click");
    await flushPromises();
    expect(addMealPlan).toHaveBeenCalledWith(1, "午餐");
  });
});
