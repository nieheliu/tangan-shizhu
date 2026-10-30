<template>
  <div>
    <el-card class="block">
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
    <el-card>
      <template #header>临期食材</template>
      <div v-loading="reminderLoading">
        <el-alert v-if="reminderError" type="error" :title="reminderError" show-icon :closable="false" />
        <el-button v-if="reminderError" @click="loadReminders">重试</el-button>
        <el-empty
          v-else-if="!reminderLoading && reminders.length === 0"
          description="没有临期或过期的食材"
        />
        <el-table v-else :data="reminders" border>
          <el-table-column prop="food_name" label="食材" />
          <el-table-column label="到期日" width="140">
            <template #default="{ row }">{{ row.expires_at ?? "—" }}</template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { fetchHealth, type HealthResponse } from "../api/health";
import { fetchReminders, type InventoryItem } from "../api/inventory";
import { statusLabel, statusType } from "../utils/inventoryStatus";

const labels: Record<string, string> = {
  postgresql: "数据库",
  neo4j: "知识图谱",
  chroma: "指南索引",
  llm: "大模型",
};

const loading = ref(true);
const error = ref("");
const health = ref<HealthResponse | null>(null);
const reminderLoading = ref(true);
const reminderError = ref("");
const reminders = ref<InventoryItem[]>([]);

const rows = computed(() => {
  const components = health.value?.components ?? {};
  return Object.entries(components).map(([key, value]) => ({
    key,
    label: labels[key] ?? key,
    value,
  }));
});

async function loadReminders() {
  reminderLoading.value = true;
  reminderError.value = "";
  try {
    const response = await fetchReminders();
    reminders.value = response.data;
  } catch {
    reminderError.value = "暂时读不到临期食材";
  } finally {
    reminderLoading.value = false;
  }
}

onMounted(async () => {
  void loadReminders();
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

<style scoped>
.block {
  margin-bottom: 16px;
}
</style>
