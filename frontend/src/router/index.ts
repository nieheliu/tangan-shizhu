import { createRouter, createWebHistory } from "vue-router";

import HomeView from "../views/HomeView.vue";
import PlaceholderView from "../views/PlaceholderView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "home", component: HomeView, meta: { title: "首页" } },
    { path: "/profile", component: PlaceholderView, meta: { title: "健康档案" } },
    { path: "/fridge", component: PlaceholderView, meta: { title: "我的冰箱" } },
    { path: "/recommend", component: PlaceholderView, meta: { title: "今日推荐" } },
    { path: "/report", component: PlaceholderView, meta: { title: "营养报告" } },
    { path: "/shopping", component: PlaceholderView, meta: { title: "购物清单" } },
    { path: "/chat", component: PlaceholderView, meta: { title: "问答" } },
    { path: "/graph", component: PlaceholderView, meta: { title: "知识图谱" } },
  ],
});

export default router;
