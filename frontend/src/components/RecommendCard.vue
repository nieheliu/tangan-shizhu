<template>
  <el-card class="card">
    <template #header>
      <div class="title">
        <router-link :to="{ path: `/recipe/${item.recipe_id}`, query: { meal } }">
          {{ item.name }}
        </router-link>
        <span>排序分 {{ item.score }}</span>
      </div>
    </template>
    <p class="reason">{{ item.reason }}</p>
    <div class="tags">
      <el-tag v-for="name in item.held_foods" :key="`held-${name}`" type="success">
        库存已有 {{ name }}
      </el-tag>
      <el-tag v-for="name in item.missing_foods" :key="`miss-${name}`" type="warning">
        需购买 {{ name }}
      </el-tag>
    </div>
    <NutritionFacts :facts="item" />
    <p v-if="item.citation_ids.length" class="citations">
      引用片段：{{ item.citation_ids.join("、") }}
    </p>
    <el-button type="primary" plain :loading="adding" @click="$emit('add')">加入今日计划</el-button>
  </el-card>
</template>

<script setup lang="ts">
import type { RecommendItem } from "../api/recommend";
import NutritionFacts from "./NutritionFacts.vue";

defineProps<{
  item: RecommendItem;
  meal: string;
  adding: boolean;
}>();

defineEmits<{ add: [] }>();
</script>

<style scoped>
.card {
  margin-bottom: 12px;
}

.title {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.title a {
  color: #1f6b3a;
  font-weight: 650;
  text-decoration: none;
}

.reason {
  margin-top: 0;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.citations {
  color: #6b7280;
  font-size: 13px;
}
</style>
