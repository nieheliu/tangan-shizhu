<template>
  <div>
    <div class="toolbar">
      <el-radio-group v-model="scope">
        <el-radio value="daily">今日</el-radio>
        <el-radio value="weekly">本周</el-radio>
      </el-radio-group>
      <el-date-picker v-model="day" type="date" value-format="YYYY-MM-DD" :clearable="false" />
      <el-button type="primary" :disabled="loading" @click="generate">生成清单</el-button>
      <el-button :disabled="loading || checkedCount === 0" @click="move">把已购买的放入冰箱</el-button>
    </div>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-button v-if="error" @click="generate">重试</el-button>
    <p v-else-if="loading">加载中</p>

    <template v-else-if="list">
      <el-alert
        v-for="food in list.excluded"
        :key="food.food_id"
        :title="`${food.food_name}是${food.reason}，没有放进清单`"
        type="warning"
        show-icon
        :closable="false"
      />
      <el-alert
        v-for="item in skipped"
        :key="item.food_name"
        :title="`${item.food_name}：${item.detail}`"
        type="warning"
        show-icon
        :closable="false"
      />
      <el-empty v-if="list.groups.length === 0" description="计划里没有还要买的食材" />
      <section v-for="group in list.groups" :key="group.category" class="group">
        <h3>{{ group.category }}</h3>
        <div v-for="item in group.items" :key="item.id" class="item">
          <el-checkbox :model-value="item.checked" @change="toggle(item, Boolean($event))">
            {{ item.food_name }}
          </el-checkbox>
          <span>{{ item.quantity }} {{ item.unit }}</span>
          <span v-if="item.unit !== '克'">{{ item.amount_g }} 克</span>
        </div>
      </section>

      <div class="manual">
        <el-select
          v-model="foodId"
          filterable
          remote
          reserve-keyword
          placeholder="手动添加食材"
          :remote-method="search"
          :loading="searching"
        >
          <el-option v-for="food in foods" :key="food.id" :label="food.name" :value="food.id" />
        </el-select>
        <el-input-number v-model="amount" :min="1" :precision="0" :step="10" />
        <span>克</span>
        <el-button :disabled="foodId == null || adding" @click="add">添加</el-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import axios from "axios";
import { computed, ref } from "vue";

import { searchFoods, type FoodOption } from "../api/foods";
import {
  addShoppingItem,
  generateShopping,
  moveShoppingToInventory,
  updateShoppingItem,
  type ShoppingItem,
  type ShoppingList,
} from "../api/shopping";

const scope = ref<"daily" | "weekly">("daily");
const day = ref(shanghaiToday());
const loading = ref(false);
const adding = ref(false);
const searching = ref(false);
const error = ref("");
const list = ref<ShoppingList | null>(null);
const skipped = ref<{ food_name: string; detail: string }[]>([]);
const foods = ref<FoodOption[]>([]);
const foodId = ref<number | null>(null);
const amount = ref(100);
let ticket = 0;

const checkedCount = computed(
  () => list.value?.groups.reduce((sum, group) => sum + group.items.filter((item) => item.checked).length, 0) ?? 0,
);

function shanghaiToday(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function message(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string" && detail) {
      return detail;
    }
  }
  return fallback;
}

async function generate() {
  const current = ++ticket;
  const selectedScope = scope.value;
  const selectedDay = day.value;
  loading.value = true;
  error.value = "";
  skipped.value = [];
  try {
    const response = await generateShopping(selectedScope, selectedDay);
    if (current !== ticket) {
      return;
    }
    list.value = response.data;
  } catch (err) {
    if (current !== ticket) {
      return;
    }
    error.value = message(err, "清单生成失败");
  } finally {
    if (current === ticket) {
      loading.value = false;
    }
  }
}

async function toggle(item: ShoppingItem, checked: boolean) {
  const previous = item.checked;
  item.checked = checked;
  try {
    const response = await updateShoppingItem(item.id, checked);
    item.checked = response.data.checked;
  } catch (err) {
    item.checked = previous;
    error.value = message(err, "没能更新勾选");
  }
}

async function move() {
  if (!list.value) {
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const response = await moveShoppingToInventory(list.value.id);
    list.value = response.data.shopping;
    skipped.value = response.data.skipped;
  } catch (err) {
    error.value = message(err, "没能放入冰箱");
  } finally {
    loading.value = false;
  }
}

async function search(keyword: string) {
  searching.value = true;
  try {
    const response = await searchFoods(keyword);
    foods.value = response.data;
  } catch {
    foods.value = [];
  } finally {
    searching.value = false;
  }
}

async function add() {
  if (!list.value || foodId.value == null) {
    return;
  }
  adding.value = true;
  error.value = "";
  try {
    const response = await addShoppingItem(list.value.id, foodId.value, amount.value);
    list.value = response.data;
    foodId.value = null;
  } catch (err) {
    error.value = message(err, "没能添加食材");
  } finally {
    adding.value = false;
  }
}
</script>

<style scoped>
.toolbar,
.manual,
.item {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.group {
  margin-top: 16px;
}
</style>
