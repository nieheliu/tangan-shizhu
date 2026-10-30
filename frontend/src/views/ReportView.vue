<template>
  <div>
    <div class="toolbar">
      <el-radio-group v-model="scope" @change="load">
        <el-radio value="daily">日报</el-radio>
        <el-radio value="weekly">周报</el-radio>
      </el-radio-group>
      <el-date-picker
        v-model="day"
        type="date"
        value-format="YYYY-MM-DD"
        :clearable="false"
        @change="load"
      />
    </div>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-button v-if="error" @click="load">重试</el-button>
    <p v-else-if="loading">加载中</p>

    <template v-else-if="shown === 'daily' && daily">
      <p class="target">
        每日目标
        {{ daily.kcal_target == null ? "—" : daily.kcal_target }}
        kcal（{{ daily.kcal_target_source }}）
      </p>
      <el-empty v-if="daily.meal_count === 0" description="这一天还没有加入计划" />
      <template v-else>
        <div v-if="showRing" ref="ringEl" class="chart" />
        <div ref="barEl" class="chart" />
        <p>
          升糖负荷
          {{ daily.gl_is_approximate ? "粗估" : "" }}
          {{ formatAmount(daily.totals.gl_estimate) }}
        </p>
        <div v-for="item in daily.items" :key="item.meal_plan_id" class="dish">
          <strong>{{ item.meal_type }} {{ item.name }}</strong>
          <span>{{ formatAmount(item.kcal) }} kcal</span>
          <span>GI {{ giText(item) }}</span>
          <span>GL {{ glText(item) }}</span>
        </div>
      </template>
      <div v-for="hint in daily.hints" :key="hint.code" class="hint">
        <p>{{ hint.message }}</p>
        <p class="basis">{{ hint.basis }}</p>
      </div>
    </template>

    <template v-else-if="shown === 'weekly' && weekly">
      <div ref="lineEl" class="chart" />
      <p v-if="weekly.kcal_average != null">有记录日期的平均热量 {{ weekly.kcal_average }} kcal</p>
      <ul class="days">
        <li v-for="item in weekly.days" :key="item.date">
          {{ item.date }} {{ item.kcal == null ? "—" : `${item.kcal} kcal` }}
        </li>
      </ul>
      <div v-for="hint in weekly.hints" :key="hint.code" class="hint">
        <p>{{ hint.message }}</p>
        <p class="basis">{{ hint.basis }}</p>
      </div>
    </template>

    <section v-if="shown && !loading && !error" class="explain">
      <p v-if="explainLoading">正在生成说明</p>
      <p v-else-if="explainError">{{ explainError }}</p>
      <p v-else-if="summary">{{ summary }}</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef } from "vue";

import { formatAmount, giText, glText } from "../api/nutrition";
import {
  explainReport,
  fetchDaily,
  fetchWeekly,
  type DailyReport,
  type ReportScope,
  type WeeklyReport,
} from "../api/reports";

interface Chart {
  setOption: (option: object) => void;
  dispose: () => void;
}

const scope = ref<ReportScope>("daily");
const day = ref(shanghaiToday());
const loading = ref(false);
const error = ref("");
const shown = ref<ReportScope | "">("");
const daily = ref<DailyReport | null>(null);
const weekly = ref<WeeklyReport | null>(null);
const summary = ref("");
const explainLoading = ref(false);
const explainError = ref("");
const ringEl = ref<HTMLDivElement | null>(null);
const barEl = ref<HTMLDivElement | null>(null);
const lineEl = ref<HTMLDivElement | null>(null);
const charts = shallowRef<Chart[]>([]);
let ticket = 0;

const showRing = computed(
  () =>
    daily.value != null &&
    daily.value.meal_count > 0 &&
    daily.value.totals.kcal != null &&
    daily.value.kcal_target != null,
);

function shanghaiToday(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function clearCharts() {
  for (const chart of charts.value) {
    chart.dispose();
  }
  charts.value = [];
}

async function paint() {
  clearCharts();
  await nextTick();
  const echarts = await import("echarts");
  const next: Chart[] = [];
  if (shown.value === "daily" && daily.value && daily.value.meal_count > 0) {
    if (showRing.value && ringEl.value && daily.value.totals.kcal != null && daily.value.kcal_target != null) {
      const kcal = daily.value.totals.kcal;
      const target = daily.value.kcal_target;
      const chart = echarts.init(ringEl.value);
      chart.setOption({
        series: [
          {
            type: "pie",
            radius: ["58%", "78%"],
            data:
              kcal > target
                ? [
                    { name: "目标内", value: target },
                    { name: "超出", value: kcal - target },
                  ]
                : [
                    { name: "计划热量", value: kcal },
                    { name: "距目标", value: target - kcal },
                  ],
          },
        ],
      });
      next.push(chart);
    }
    if (barEl.value) {
      const totals = daily.value.totals;
      const chart = echarts.init(barEl.value);
      chart.setOption({
        xAxis: { type: "category", name: "克", data: ["碳水", "蛋白质", "脂肪", "膳食纤维"] },
        yAxis: { type: "value" },
        series: [
          {
            type: "bar",
            data: [totals.carb_g, totals.protein_g, totals.fat_g, totals.fiber_g],
          },
        ],
      });
      next.push(chart);
    }
  }
  if (shown.value === "weekly" && weekly.value && lineEl.value) {
    const chart = echarts.init(lineEl.value);
    chart.setOption({
      xAxis: { type: "category", data: weekly.value.days.map((item) => item.date) },
      yAxis: { type: "value" },
      series: [
        {
          name: "热量",
          type: "line",
          connectNulls: false,
          data: weekly.value.days.map((item) => item.kcal),
        },
      ],
    });
    next.push(chart);
  }
  charts.value = next;
}

async function loadExplain(current: number, selectedScope: ReportScope, selectedDay: string) {
  explainLoading.value = true;
  explainError.value = "";
  summary.value = "";
  try {
    const response = await explainReport(selectedScope, selectedDay);
    if (current !== ticket) {
      return;
    }
    summary.value = response.data.summary;
  } catch {
    if (current !== ticket) {
      return;
    }
    explainError.value = "说明暂时无法生成";
  } finally {
    if (current === ticket) {
      explainLoading.value = false;
    }
  }
}

async function load() {
  const current = ++ticket;
  const selectedScope = scope.value;
  const selectedDay = day.value;
  loading.value = true;
  error.value = "";
  summary.value = "";
  explainError.value = "";
  try {
    if (selectedScope === "daily") {
      const response = await fetchDaily(selectedDay);
      if (current !== ticket) {
        return;
      }
      daily.value = response.data;
      weekly.value = null;
    } else {
      const response = await fetchWeekly(selectedDay);
      if (current !== ticket) {
        return;
      }
      weekly.value = response.data;
      daily.value = null;
    }
    shown.value = selectedScope;
    loading.value = false;
    await paint();
    void loadExplain(current, selectedScope, selectedDay);
  } catch {
    if (current !== ticket) {
      return;
    }
    shown.value = "";
    loading.value = false;
    error.value = "报告加载失败";
  }
}

onMounted(() => {
  void load();
});

onBeforeUnmount(() => {
  clearCharts();
});
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.chart {
  width: 100%;
  height: 280px;
  margin-bottom: 12px;
}

.dish,
.hint,
.target,
.explain {
  margin-bottom: 8px;
}

.dish span {
  margin-left: 12px;
}

.days {
  padding-left: 18px;
}

.basis {
  color: #5c6b62;
  font-size: 13px;
}
</style>
