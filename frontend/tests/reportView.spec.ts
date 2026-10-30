import { flushPromises, mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { explainReport, fetchDaily, fetchWeekly, type DailyReport, type WeeklyReport } from "../src/api/reports";
import ReportView from "../src/views/ReportView.vue";

const setOption = vi.fn();

vi.mock("echarts", () => ({
  init: vi.fn(() => ({
    setOption,
    resize: vi.fn(),
    dispose: vi.fn(),
  })),
}));

vi.mock("../src/api/reports", () => ({
  fetchDaily: vi.fn(),
  fetchWeekly: vi.fn(),
  explainReport: vi.fn(),
}));

function dailyPayload(extra: Partial<DailyReport> = {}): DailyReport {
  return {
    date: "2026-10-30",
    meal_count: 1,
    kcal_target: 1650,
    kcal_target_source: "待核对",
    totals: {
      kcal: 202.2,
      carb_g: 40,
      protein_g: 6,
      fat_g: 2,
      fiber_g: 3,
      sodium_mg: 1,
      gl_estimate: 10,
    },
    energy_ratios: {
      carb: 80,
      protein: 12,
      fat: 8,
      factor_source: "待核对",
      target_range: null,
    },
    fiber_target_g: null,
    fiber_target_source: "待核对",
    fiber_met_days: null,
    gl_is_approximate: true,
    hints: [
      {
        code: "kcal_under",
        message: "今日热量 202.2 kcal，低于每日目标 1650 kcal。",
        basis: "比较的是计划内食谱热量合计和档案中的每日热量目标。目标估算系数来源为待核对。",
      },
      {
        code: "ratio_ready",
        message: "碳水供能比 80%，蛋白质 12%，脂肪 8%。",
        basis: "供能比按碳水、蛋白质每克 4 kcal、脂肪每克 9 kcal 估算，系数来源待核对。目标区间尚未对照指南页码，这里不显示区间。",
      },
      {
        code: "fiber_unverified",
        message: "膳食纤维合计 3 g。达标克数待核对，所以不计算达标天数。",
        basis: "达标标准还没有核对过的指南页码，不能把未核对的克数当成达标线。",
      },
    ],
    items: [
      {
        meal_plan_id: 1,
        recipe_id: 17,
        name: "荞麦饭",
        meal_type: "午餐",
        servings: 1,
        kcal: 202.2,
        carb_g: 40,
        protein_g: 6,
        fat_g: 2,
        fiber_g: 3,
        sodium_mg: 1,
        oil_estimated: false,
        gi_band_label: null,
        gi_band_source: "待核对",
        gl_estimate: 10,
        gl_is_approximate: true,
      },
    ],
    ...extra,
  };
}

function weeklyPayload(): WeeklyReport {
  return {
    start: "2026-10-24",
    end: "2026-10-30",
    days: [
      { date: "2026-10-28", kcal: 100, carb_energy_ratio: 50, fiber_g: 3 },
      { date: "2026-10-29", kcal: null, carb_energy_ratio: null, fiber_g: null },
      { date: "2026-10-30", kcal: 300, carb_energy_ratio: 50, fiber_g: 4 },
    ],
    kcal_average: 200,
    days_with_kcal: 2,
    carb_energy_ratio: 50,
    energy_factor_source: "待核对",
    target_range: null,
    fiber_target_g: null,
    fiber_target_source: "待核对",
    fiber_met_days: null,
    hints: [
      {
        code: "week_kcal",
        message: "近 7 天里有 2 天可以合计热量，这些天的平均热量是 200 kcal。",
        basis: "没有计划或热量缺失的日期不计入平均，也不按 0 处理。",
      },
      {
        code: "fiber_unverified",
        message: "膳食纤维达标天数未统计，达标克数待核对。",
        basis: "达标标准还没有核对过的指南页码。",
      },
    ],
  };
}

async function mountPage() {
  const wrapper = mount(ReportView, {
    global: { plugins: [ElementPlus] },
  });
  await flushPromises();
  return wrapper;
}

function shanghaiToday(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

describe("report page", () => {
  beforeEach(() => {
    setOption.mockClear();
    vi.mocked(fetchDaily).mockReset();
    vi.mocked(fetchWeekly).mockReset();
    vi.mocked(explainReport).mockReset();
    vi.mocked(explainReport).mockResolvedValue({
      data: { summary: "今日热量 202.2 kcal。", citation_ids: [], rag: "down" },
    } as never);
  });

  it("shows the daily comparison without a target range", async () => {
    vi.mocked(fetchDaily).mockResolvedValue({ data: dailyPayload() } as never);
    const wrapper = await mountPage();
    const text = wrapper.text();
    expect(fetchDaily).toHaveBeenCalledWith(shanghaiToday());
    expect(text).toContain("低于每日目标");
    expect(text).toContain("待核对");
    expect(text).toContain("粗估");
    expect(text).toContain("荞麦饭");
    expect(text).not.toMatch(/\d+%\s*[~～\-—到至]\s*\d+/);
    const pie = setOption.mock.calls.map((call) => call[0]).find((option) => option.series[0].type === "pie");
    expect(pie.series[0].data[0].value).toBe(202.2);
  });

  it("hides the ring when the day has no kcal", async () => {
    vi.mocked(fetchDaily).mockResolvedValue({
      data: dailyPayload({
        totals: {
          kcal: null,
          carb_g: null,
          protein_g: null,
          fat_g: null,
          fiber_g: null,
          sodium_mg: null,
          gl_estimate: null,
        },
        hints: [
          {
            code: "kcal_incomplete",
            message: "有食谱缺少热量，今日热量无法合计，也不能和目标比较。",
            basis: "只要有一道菜的热量是空的，当天合计就留空，不用 0 代替。",
          },
        ],
      }),
    } as never);
    const wrapper = await mountPage();
    expect(wrapper.text()).toContain("缺少热量");
    expect(wrapper.text()).not.toContain("低于每日目标");
    const types = setOption.mock.calls.map((call) => call[0].series[0].type);
    expect(types).not.toContain("pie");
    const bar = setOption.mock.calls.map((call) => call[0]).find((option) => option.series[0].type === "bar");
    expect(bar.series[0].data).toEqual([null, null, null, null]);
  });

  it("draws missing week days as gaps", async () => {
    vi.mocked(fetchDaily).mockResolvedValue({ data: dailyPayload() } as never);
    vi.mocked(fetchWeekly).mockResolvedValue({ data: weeklyPayload() } as never);
    const wrapper = await mountPage();
    const weekly = wrapper.findAll("input[type='radio']")[1];
    await weekly.setValue(true);
    await flushPromises();
    expect(fetchWeekly).toHaveBeenCalledWith(shanghaiToday());
    expect(wrapper.text()).toContain("达标天数未统计");
    expect(wrapper.text()).toContain("待核对");
    const line = setOption.mock.calls.map((call) => call[0]).find((option) => option.series[0].type === "line");
    expect(line.series[0].connectNulls).toBe(false);
    expect(line.series[0].data).toEqual([100, null, 300]);
  });

  it("shows an empty day and can retry after an error", async () => {
    vi.mocked(fetchDaily)
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce({
        data: dailyPayload({
          meal_count: 0,
          totals: {
            kcal: null,
            carb_g: null,
            protein_g: null,
            fat_g: null,
            fiber_g: null,
            sodium_mg: null,
            gl_estimate: null,
          },
          items: [],
          hints: [
            {
              code: "plan_empty",
              message: "这一天还没有加入计划。",
              basis: "统计范围是当天计划里的食谱，不含计划外的饮食。",
            },
          ],
        }),
      } as never);
    const wrapper = await mountPage();
    expect(wrapper.text()).toContain("报告加载失败");
    const retry = wrapper.findAll("button").find((button) => button.text() === "重试");
    await retry?.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("这一天还没有加入计划");
    expect(setOption).not.toHaveBeenCalled();
  });

  it("keeps the numbers when the explanation fails", async () => {
    vi.mocked(fetchDaily).mockResolvedValue({ data: dailyPayload() } as never);
    vi.mocked(explainReport).mockRejectedValue(new Error("cloud"));
    const wrapper = await mountPage();
    expect(wrapper.text()).toContain("低于每日目标");
    expect(wrapper.text()).toContain("说明暂时无法生成");
  });
});
