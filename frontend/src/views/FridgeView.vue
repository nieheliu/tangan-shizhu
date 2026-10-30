<template>
  <div>
  <div v-loading="loading">
    <el-alert v-if="loadError" :title="loadError" type="error" show-icon :closable="false" />
    <el-button v-if="loadError" @click="load">重试</el-button>
    <template v-else-if="!loading">
      <div class="toolbar">
        <el-button type="primary" @click="openCreate">新增食材</el-button>
      </div>
      <el-empty v-if="items.length === 0" description="冰箱还是空的" />
      <el-table v-else :data="items" border>
        <el-table-column prop="food_name" label="食材" />
        <el-table-column prop="quantity" label="数量" width="90" />
        <el-table-column prop="unit" label="单位" width="80" />
        <el-table-column label="约克数" width="100">
          <template #default="{ row }">{{ row.grams ?? "—" }}</template>
        </el-table-column>
        <el-table-column label="购买日期" width="120">
          <template #default="{ row }">{{ row.purchased_at ?? "—" }}</template>
        </el-table-column>
        <el-table-column label="到期日" width="120">
          <template #default="{ row }">{{ row.expires_at ?? "—" }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </div>

    <el-dialog v-model="dialogOpen" :title="editingId == null ? '新增食材' : '编辑食材'" width="480px">
      <el-alert v-if="saveError" :title="saveError" type="error" show-icon :closable="false" />
      <el-form label-width="90px">
        <el-form-item label="食材">
          <el-select
            v-model="form.food_id"
            filterable
            remote
            reserve-keyword
            placeholder="输入食材名"
            :remote-method="search"
            :loading="searching"
          >
            <el-option v-for="food in foodOptions" :key="food.id" :label="food.name" :value="food.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="form.quantity" :min="0.1" :precision="1" :step="10" />
        </el-form-item>
        <el-form-item label="单位">
          <el-input v-model="form.unit" placeholder="克" />
          <p class="hint">没有换算的单位不能保存，请改成克。</p>
        </el-form-item>
        <el-form-item label="购买日期">
          <el-date-picker v-model="form.purchased_at" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="到期日">
          <el-date-picker v-model="form.expires_at" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import axios from "axios";
import { ElMessageBox } from "element-plus";
import { onMounted, reactive, ref } from "vue";

import { searchFoods, type FoodOption } from "../api/foods";
import {
  createInventory,
  deleteInventory,
  fetchInventory,
  updateInventory,
  type InventoryItem,
} from "../api/inventory";
import { statusLabel, statusType } from "../utils/inventoryStatus";

const loading = ref(true);
const loadError = ref("");
const items = ref<InventoryItem[]>([]);
const dialogOpen = ref(false);
const saving = ref(false);
const saveError = ref("");
const searching = ref(false);
const editingId = ref<number | null>(null);
const foodOptions = ref<FoodOption[]>([]);
const form = reactive({
  food_id: undefined as number | undefined,
  quantity: undefined as number | undefined,
  unit: "克",
  purchased_at: "" as string | null,
  expires_at: "" as string | null,
});

function resetForm() {
  form.food_id = undefined;
  form.quantity = undefined;
  form.unit = "克";
  form.purchased_at = "";
  form.expires_at = "";
  saveError.value = "";
  foodOptions.value = [];
}

function openCreate() {
  editingId.value = null;
  resetForm();
  dialogOpen.value = true;
}

function openEdit(row: InventoryItem) {
  editingId.value = row.id;
  form.food_id = row.food_id;
  form.quantity = row.quantity;
  form.unit = row.unit;
  form.purchased_at = row.purchased_at ?? "";
  form.expires_at = row.expires_at ?? "";
  saveError.value = "";
  foodOptions.value = [{ id: row.food_id, name: row.food_name, category: null, units: [row.unit] }];
  dialogOpen.value = true;
}

async function search(keyword: string) {
  const text = keyword.trim();
  if (!text) {
    return;
  }
  searching.value = true;
  try {
    const { data } = await searchFoods(text);
    foodOptions.value = data;
  } catch {
    foodOptions.value = [];
  } finally {
    searching.value = false;
  }
}

async function load(showLoading = true) {
  if (showLoading) {
    loading.value = true;
  }
  loadError.value = "";
  try {
    const { data } = await fetchInventory();
    items.value = data;
  } catch {
    loadError.value = "暂时读不到冰箱";
  } finally {
    loading.value = false;
  }
}

function messageFrom(caught: unknown) {
  if (axios.isAxiosError(caught)) {
    const detail = caught.response?.data?.detail;
    if (typeof detail === "string") {
      return detail;
    }
  }
  return "保存失败，请检查填写内容";
}

async function save() {
  saveError.value = "";
  if (form.food_id == null || form.quantity == null || !form.unit.trim()) {
    saveError.value = "请选择食材，并填写数量和单位";
    return;
  }
  const payload = {
    food_id: form.food_id,
    quantity: form.quantity,
    unit: form.unit.trim(),
    purchased_at: form.purchased_at || null,
    expires_at: form.expires_at || null,
  };
  saving.value = true;
  try {
    if (editingId.value == null) {
      await createInventory(payload);
    } else {
      await updateInventory(editingId.value, payload);
    }
    dialogOpen.value = false;
    await load(false);
  } catch (caught) {
    saveError.value = messageFrom(caught);
  } finally {
    saving.value = false;
  }
}

async function remove(row: InventoryItem) {
  try {
    await ElMessageBox.confirm(`删除 ${row.food_name}？`, "删除库存", { type: "warning" });
  } catch {
    return;
  }
  try {
    await deleteInventory(row.id);
    await load();
  } catch {
    loadError.value = "删除失败";
  }
}

onMounted(() => {
  void load();
});
</script>

<style scoped>
.toolbar {
  margin-bottom: 12px;
}

.hint {
  margin: 6px 0 0;
  color: #5c6b62;
  font-size: 12px;
  line-height: 1.4;
}
</style>
