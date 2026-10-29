<template>
  <el-empty :description="`${title}将在后续任务中完成`" />
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const title = computed(() => String(route.meta.title ?? "该页面"));
</script>
