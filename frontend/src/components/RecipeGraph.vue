<template>
  <div>
    <el-alert
      v-if="graph !== 'up'"
      title="图谱暂时不可用，关系稍后再看"
      type="info"
      show-icon
      :closable="false"
    />
    <el-empty v-else-if="links.length === 0" description="这道菜的食材暂时没有图谱关系" />
    <div v-else class="graph">
      <div class="node recipe">{{ name }}</div>
      <div v-for="(link, index) in links" :key="index" class="link">
        <span class="node">{{ link.food_name }}</span>
        <span class="edge">{{ phrase(link) }}</span>
        <span class="node">{{ link.other_name }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RecipeGraphLink } from "../api/recipes";

defineProps<{
  name: string;
  graph: string;
  links: RecipeGraphLink[];
}>();

const relationLabels: Record<string, string> = {
  RECOMMEND: "推荐",
  AVOID: "避免",
  LIMIT: "限量",
  CONTAINS: "含有",
  COOKED_BY: "做法",
  AVOID_METHOD: "避免做法",
  SUBSTITUTE: "可替换",
};

function phrase(link: RecipeGraphLink) {
  const label = relationLabels[link.relation] ?? link.relation;
  if (link.direction === "in") {
    return `← ${label} ←`;
  }
  return `→ ${label} →`;
}
</script>

<style scoped>
.graph {
  display: grid;
  gap: 10px;
}

.node {
  display: inline-block;
  padding: 4px 10px;
  border: 1px solid #c9dfd0;
  border-radius: 999px;
  background: #fff;
}

.recipe {
  background: #e7f5ec;
  font-weight: 600;
}

.link {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.edge {
  color: #2f7d4a;
  font-size: 13px;
}
</style>
