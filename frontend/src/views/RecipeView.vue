<template>
  <div v-loading="loading">
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-button v-if="error" @click="load">重试</el-button>
    <template v-else-if="recipe">
      <div class="heading">
        <div>
          <h2>{{ recipe.name }}</h2>
          <p class="meta">
            {{ recipe.meal_types.join("、") || "未标餐次" }}
            <span v-if="recipe.cooking_method"> · {{ recipe.cooking_method }}</span>
            <span> · {{ recipe.servings }} 份</span>
          </p>
          <p v-if="recipe.source" class="meta">来源：{{ recipe.source }}</p>
        </div>
        <el-button type="primary" :loading="adding" @click="add">加入{{ meal }}计划</el-button>
      </div>
      <img v-if="recipe.image_url" :src="recipe.image_url" :alt="recipe.name" class="photo" />

      <el-card>
        <template #header>食材</template>
        <el-empty v-if="recipe.ingredients.length === 0" description="还没有食材" />
        <el-table v-else :data="recipe.ingredients" border>
          <el-table-column prop="name" label="食材" />
          <el-table-column label="克数" width="120">
            <template #default="{ row }">{{ row.amount_g }}</template>
          </el-table-column>
          <el-table-column label="主食" width="100">
            <template #default="{ row }">{{ row.is_main ? "是" : "否" }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card>
        <template #header>步骤</template>
        <el-empty v-if="!recipe.steps" description="还没有步骤" />
        <p v-else class="steps">{{ recipe.steps }}</p>
      </el-card>

      <el-card>
        <template #header>每份营养</template>
        <NutritionFacts :facts="recipe" />
      </el-card>

      <el-card>
        <template #header>食材关系</template>
        <RecipeGraph :name="recipe.name" :graph="recipe.graph" :links="recipe.links" />
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import axios from "axios";
import { ElMessage } from "element-plus";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";

import { addMealPlan } from "../api/mealPlans";
import { fetchRecipe, type RecipeDetail } from "../api/recipes";
import NutritionFacts from "../components/NutritionFacts.vue";
import RecipeGraph from "../components/RecipeGraph.vue";

const meals = ["早餐", "午餐", "晚餐", "加餐"];
const route = useRoute();
const loading = ref(true);
const error = ref("");
const recipe = ref<RecipeDetail | null>(null);
const adding = ref(false);

const recipeId = computed(() => Number(route.params.id));
const meal = computed(() => {
  const value = route.query.meal;
  return typeof value === "string" && meals.includes(value) ? value : "午餐";
});

function failureText(errorValue: unknown, fallback: string) {
  if (axios.isAxiosError(errorValue)) {
    const detail = (errorValue.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string" && detail) {
      return detail;
    }
  }
  return fallback;
}

async function load() {
  loading.value = true;
  error.value = "";
  recipe.value = null;
  if (!Number.isInteger(recipeId.value) || recipeId.value <= 0) {
    error.value = "找不到这道食谱";
    loading.value = false;
    return;
  }
  try {
    const response = await fetchRecipe(recipeId.value);
    recipe.value = response.data;
  } catch (caught) {
    error.value = failureText(caught, "暂时读不到这道食谱");
  } finally {
    loading.value = false;
  }
}

async function add() {
  if (!recipe.value) {
    return;
  }
  adding.value = true;
  try {
    const response = await addMealPlan(recipe.value.id, meal.value);
    const text = response.data.already_added ? "这道菜已经在今日计划里" : "已加入今日计划";
    ElMessage.success(text);
  } catch (caught) {
    ElMessage.error(failureText(caught, "暂时无法加入计划"));
  } finally {
    adding.value = false;
  }
}

onMounted(() => {
  void load();
});

watch(() => route.params.id, () => {
  void load();
});
</script>

<style scoped>
.heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

h2 {
  margin: 0 0 4px;
}

.meta {
  margin: 0 0 4px;
  color: #6b7280;
}

.photo {
  max-width: 320px;
  border-radius: 8px;
}

.el-card {
  margin-top: 16px;
}

.steps {
  white-space: pre-wrap;
  margin: 0;
}
</style>
