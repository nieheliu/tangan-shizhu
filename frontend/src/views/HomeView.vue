<template>
  <el-card>
    <template #header>服务状态</template>
    <div v-loading="loading">
      <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" />
      <el-empty v-else-if="!loading && rows.length === 0" description="还没有健康检查结果" />
      <el-descriptions v-else :column="1" border>
        <el-descriptions-item v-for="row in rows" :key="row.key" :label="row.label">
          <el-tag :type="row.value === 'up' ? 'success' : 'info'">{{ row.value }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { fetchHealth, type HealthResponse } from "../api/health";

const labels: Record<string, string> = {
  postgresql: "数据库",
  neo4j: "知识图谱",
  chroma: "指南索引",
  llm: "大模型",
};

const loading = ref(true);
const error = ref("");
const health = ref<HealthResponse | null>(null);

const rows = computed(() => {
  const components = health.value?.components ?? {};
  return Object.entries(components).map(([key, value]) => ({
    key,
    label: labels[key] ?? key,
    value,
  }));
});

onMounted(async () => {
  try {
    const response = await fetchHealth();
    health.value = response.data;
  } catch {
    error.value = "暂时连不上后端，请确认服务已在 127.0.0.1:8000 启动";
  } finally {
    loading.value = false;
  }
});
</script>
