import { flushPromises, mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchFoodFacts, fetchNeighbors, type Neighborhood } from "../src/api/graph";
import GraphView from "../src/views/GraphView.vue";

const setOption = vi.fn();
const on = vi.fn();

vi.mock("echarts", () => ({
  init: vi.fn(() => ({
    setOption,
    on,
    dispose: vi.fn(),
  })),
}));

vi.mock("../src/api/graph", () => ({
  fetchNeighbors: vi.fn(),
  fetchFoodFacts: vi.fn(),
}));

function payload(): Neighborhood {
  return {
    graph: "up",
    center: { id: "Food:荞麦", name: "荞麦", label: "Food", pg_id: 5 },
    nodes: [
      { id: "Food:荞麦", name: "荞麦", label: "Food", pg_id: 5 },
      { id: "Disease:2型糖尿病", name: "2型糖尿病", label: "Disease", pg_id: null },
    ],
    links: [
      {
        source: "Disease:2型糖尿病",
        target: "Food:荞麦",
        relation: "RECOMMEND",
        reason: "优选全谷物",
        citation: "指南第6页",
      },
    ],
  };
}

async function mountPage() {
  const wrapper = mount(GraphView, { global: { plugins: [ElementPlus] } });
  await flushPromises();
  return wrapper;
}

describe("graph page", () => {
  beforeEach(() => {
    setOption.mockClear();
    on.mockClear();
    vi.mocked(fetchNeighbors).mockReset();
    vi.mocked(fetchFoodFacts).mockReset();
  });

  it("draws relations and loads nutrition only after a food is chosen", async () => {
    vi.mocked(fetchNeighbors).mockResolvedValue({ data: payload() } as never);
    vi.mocked(fetchFoodFacts).mockResolvedValue({
      data: {
        pg_id: 5,
        name: "荞麦",
        category: "谷类",
        per_g: 100,
        kcal: 335,
        carb_g: 73,
        protein_g: 9,
        fat_g: null,
        fiber_g: null,
        sodium_mg: null,
        gi: null,
        gi_source: "待核对",
        nutrient_source: "成分表",
      },
    } as never);
    const wrapper = await mountPage();
    await wrapper.get("input").setValue("荞麦");
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(fetchNeighbors).toHaveBeenCalledWith("荞麦", 2);
    expect(wrapper.text()).toContain("推荐");
    expect(wrapper.text()).toContain("指南第6页");
    expect(wrapper.text()).not.toContain("335");
    const option = setOption.mock.calls[0][0];
    expect(option.series[0].layout).toBe("force");
    expect(JSON.stringify(option.series[0].data)).not.toContain("kcal");
    expect(JSON.stringify(option.series[0].data)).not.toContain("gi");
    const food = wrapper.findAll("button").find((button) => button.text() === "荞麦");
    await food?.trigger("click");
    await flushPromises();
    expect(fetchFoodFacts).toHaveBeenCalledWith(5);
    expect(wrapper.text()).toContain("GI —");
    expect(wrapper.text()).toContain("待核对");
    expect(wrapper.text()).toContain("335");
  });

  it("shows an empty result and can retry after an error", async () => {
    vi.mocked(fetchNeighbors)
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce({
        data: { graph: "up", center: null, nodes: [], links: [] },
      } as never);
    const wrapper = await mountPage();
    await wrapper.get("input").setValue("没有");
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("图谱查询失败");
    const retry = wrapper.findAll("button").find((button) => button.text() === "重试");
    await retry?.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("没有找到这个食材或疾病");
    expect(setOption).not.toHaveBeenCalled();
  });
});
