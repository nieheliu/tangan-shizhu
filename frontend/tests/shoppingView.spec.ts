import { flushPromises, mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { searchFoods } from "../src/api/foods";
import {
  addShoppingItem,
  generateShopping,
  moveShoppingToInventory,
  updateShoppingItem,
  type ShoppingList,
} from "../src/api/shopping";
import ShoppingView from "../src/views/ShoppingView.vue";

vi.mock("../src/api/shopping", () => ({
  generateShopping: vi.fn(),
  addShoppingItem: vi.fn(),
  updateShoppingItem: vi.fn(),
  moveShoppingToInventory: vi.fn(),
}));

vi.mock("../src/api/foods", () => ({
  searchFoods: vi.fn(),
}));

function payload(extra: Partial<ShoppingList> = {}): ShoppingList {
  return {
    id: 4,
    start: "2026-10-30",
    end: "2026-10-30",
    groups: [
      {
        category: "主食",
        items: [
          {
            id: 8,
            food_id: 17,
            food_name: "荞麦",
            category: "主食",
            amount_g: 60,
            quantity: 60,
            unit: "克",
            checked: false,
          },
        ],
      },
    ],
    excluded: [{ food_id: 3, food_name: "虾仁", reason: "过敏原" }],
    ...extra,
  };
}

async function mountPage() {
  const wrapper = mount(ShoppingView, { global: { plugins: [ElementPlus] } });
  await flushPromises();
  return wrapper;
}

describe("shopping page", () => {
  beforeEach(() => {
    vi.mocked(generateShopping).mockReset();
    vi.mocked(addShoppingItem).mockReset();
    vi.mocked(updateShoppingItem).mockReset();
    vi.mocked(moveShoppingToInventory).mockReset();
    vi.mocked(searchFoods).mockReset();
  });

  it("shows purchases and keeps allergens off the buy list", async () => {
    vi.mocked(generateShopping).mockResolvedValue({ data: payload() } as never);
    const wrapper = await mountPage();
    await wrapper.get("button").trigger("click");
    await flushPromises();
    const text = wrapper.text();
    expect(text).toContain("荞麦");
    expect(text).toContain("60 克");
    expect(text).toContain("虾仁是过敏原，没有放进清单");
    expect(text.indexOf("虾仁")).toBeLessThan(text.indexOf("荞麦"));
  });

  it("shows an empty plan and can retry after an error", async () => {
    vi.mocked(generateShopping)
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce({
        data: payload({ groups: [], excluded: [] }),
      } as never);
    const wrapper = await mountPage();
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("清单生成失败");
    const retry = wrapper.findAll("button").find((button) => button.text() === "重试");
    await retry?.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("计划里没有还要买的食材");
  });

  it("moves checked foods into the fridge", async () => {
    vi.mocked(generateShopping).mockResolvedValue({ data: payload() } as never);
    vi.mocked(updateShoppingItem).mockResolvedValue({
      data: { ...payload().groups[0].items[0], checked: true },
    } as never);
    vi.mocked(moveShoppingToInventory).mockResolvedValue({
      data: {
        added: [],
        skipped: [],
        shopping: payload({ groups: [] }),
      },
    } as never);
    const wrapper = await mountPage();
    await wrapper.get("button").trigger("click");
    await flushPromises();
    await wrapper.get("input[type='checkbox']").setValue(true);
    await flushPromises();
    const move = wrapper.findAll("button").find((button) => button.text() === "把已购买的放入冰箱");
    await move?.trigger("click");
    await flushPromises();
    expect(updateShoppingItem).toHaveBeenCalledWith(8, true);
    expect(moveShoppingToInventory).toHaveBeenCalledWith(4);
    expect(wrapper.text()).toContain("计划里没有还要买的食材");
  });
});
