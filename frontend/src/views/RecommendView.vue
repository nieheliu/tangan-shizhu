<template>
  <div v-loading="loading">
    <div class="toolbar">
      <el-radio-group v-model="mealType">
        <el-radio v-for="meal in meals" :key="meal" :value="meal">{{ meal }}</el-radio>
      </el-radio-group>
      <el-checkbox v-model="onlyInventory">只用冰箱里的食材</el-checkbox>
      <el-button type="primary" :disabled="loading" @click="generate">生成推荐</el-button>
      <el-button :disabled="loading || filtersChanged || shown.length === 0" @click="swap">
        换一批
      </el-button>
    </div>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-button v-if="error" @click="generate">重试</el-button>

    <template v-else-if="result">
      <div class="status">
        <el-tag :type="result.graph === 'up' ? 'success' : 'info'">图谱 {{ result.graph }}</el-tag>
        <el-tag :type="result.rag === 'up' ? 'success' : 'info'">检索 {{ result.rag }}</el-tag>
      </div>
      <el-alert
        v-if="result.blocked"
        :title="result.block_message || '请就医'"
        type="warning"
        show-icon
        :closable="false"
      />
      <template v-else>
        <template v-if="loadedOnly">
          <h3>严格结果</h3>
          <el-empty v-if="result.strict.length === 0" description="没有能完全用冰箱食材做的菜" />
          <RecommendCard
            v-for="item in result.strict"
            :key="item.recipe_id"
            :item="item"
            :meal="loadedMeal"
            :adding="addingId === item.recipe_id"
            @add="add(item)"
          />
          <h3>放宽后需购买</h3>
          <el-empty v-if="result.relaxed.length === 0" description="没有需要另外购买食材的菜" />
          <RecommendCard
            v-for="item in result.relaxed"
            :key="item.recipe_id"
            :item="item"
            :meal="loadedMeal"
            :adding="addingId === item.recipe_id"
            @add="add(item)"
          />
        </template>
        <template v-else>
          <el-empty v-if="result.strict.length === 0" description="这次没有可推荐的菜" />
          <RecommendCard
            v-for="item in result.strict"
            :key="item.recipe_id"
            :item="item"
            :meal="loadedMeal"
            :adding="addingId === item.recipe_id"
            @add="add(item)"
          />
        </template>
        <el-collapse v-if="result.rejected.length">
          <el-collapse-item title="为什么不推荐" name="rejected">
            <div v-for="item in result.rejected" :key="item.recipe_id" class="rejected">
              <strong>{{ item.name }}</strong>
              <p v-for="reason in item.reasons" :key="reason.rule_id">
                {{ reason.rule_id }}：{{ reason.message }}
                <span class="source">出处：{{ reason.source }}</span>
              </p>
            </div>
          </el-collapse-item>
        </el-collapse>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import axios from "axios";
import { ElMessage } from "element-plus";
import { computed, onMounted, ref } from "vue";

import { addMealPlan } from "../api/mealPlans";
import { fetchRecommend, type RecommendItem, type RecommendResponse } from "../api/recommend";
import RecommendCard from "../components/RecommendCard.vue";

const meals = ["早餐", "午餐", "晚餐", "加餐"] as const;

const mealType = ref<(typeof meals)[number]>("午餐");
const onlyInventory = ref(false);
const excludeIds = ref<number[]>([]);
const loading = ref(false);
const error = ref("");
const result = ref<RecommendResponse | null>(null);
const loadedMeal = ref("午餐");
const loadedOnly = ref(false);
const addingId = ref<number | null>(null);
let requestSeq = 0;

const shown = computed(() => {
  if (!result.value || result.value.blocked) {
    return [];
  }
  return [...result.value.strict, ...result.value.relaxed];
});

const filtersChanged = computed(
  () => mealType.value !== loadedMeal.value || onlyInventory.value !== loadedOnly.value,
);

function failureText(errorValue: unknown, fallback: string) {
  if (axios.isAxiosError(errorValue)) {
    const detail = (errorValue.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string" && detail) {
      return detail;
    }
  }
  return fallback;
}

async function load(nextExclude: number[]) {
  const seq = ++requestSeq;
  const meal = mealType.value;
  const only = onlyInventory.value;
  loading.value = true;
  error.value = "";
  try {
    const response = await fetchRecommend({
      meal_type: meal,
      only_inventory: only,
      exclude_ids: nextExclude,
    });
    if (seq !== requestSeq) {
      return;
    }
    result.value = response.data;
    excludeIds.value = nextExclude;
    loadedMeal.value = meal;
    loadedOnly.value = only;
  } catch (caught) {
    if (seq !== requestSeq) {
      return;
    }
    result.value = null;
    error.value = failureText(caught, "暂时无法生成推荐");
  } finally {
    if (seq === requestSeq) {
      loading.value = false;
    }
  }
}

function generate() {
  void load([]);
}

function swap() {
  void load([...excludeIds.value, ...shown.value.map((item) => item.recipe_id)]);
}

async function add(item: RecommendItem) {
  addingId.value = item.recipe_id;
  try {
    const response = await addMealPlan(item.recipe_id, loadedMeal.value);
    const text = response.data.already_added ? "这道菜已经在今日计划里" : "已加入今日计划";
    ElMessage.success(text);
  } catch (caught) {
    ElMessage.error(failureText(caught, "暂时无法加入计划"));
  } finally {
    addingId.value = null;
  }
}

onMounted(() => {
  void load([]);
});
</script>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.status {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

h3 {
  margin: 8px 0 12px;
}

.source {
  margin-left: 8px;
  color: #6b7280;
}

.rejected + .rejected {
  margin-top: 8px;
}
</style>
