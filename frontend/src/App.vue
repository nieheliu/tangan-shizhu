<template>
  <el-container class="layout">
    <el-aside width="220px">
      <div class="brand">糖安食助</div>
      <el-menu router :default-active="route.path">
        <el-menu-item index="/">首页</el-menu-item>
        <el-menu-item index="/profile">健康档案</el-menu-item>
        <el-menu-item index="/fridge">我的冰箱</el-menu-item>
        <el-menu-item index="/recommend">今日推荐</el-menu-item>
        <el-menu-item index="/report">营养报告</el-menu-item>
        <el-menu-item index="/shopping">购物清单</el-menu-item>
        <el-menu-item index="/chat">问答</el-menu-item>
        <el-menu-item index="/graph">知识图谱</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header>{{ title }}</el-header>
      <el-main>
        <router-view />
      </el-main>
      <el-footer>
        <DisclaimerFooter />
      </el-footer>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

import DisclaimerFooter from "./components/DisclaimerFooter.vue";

const route = useRoute();
const title = computed(() => String(route.meta.title ?? "糖安食助"));
</script>
