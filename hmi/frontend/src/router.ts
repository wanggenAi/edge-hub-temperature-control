import { createRouter, createWebHistory } from "vue-router";

import { getStoredToken } from "./composables/useAuth";
import AIPage from "./pages/AIPage.vue";
import HistoryPage from "./pages/HistoryPage.vue";
import LoginPage from "./pages/LoginPage.vue";
import OverviewPage from "./pages/OverviewPage.vue";
import ParamsPage from "./pages/ParamsPage.vue";
import RealtimePage from "./pages/RealtimePage.vue";
import UserPage from "./pages/UserPage.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: LoginPage, meta: { public: true } },
    { path: "/", name: "overview", component: OverviewPage },
    { path: "/realtime", name: "realtime", component: RealtimePage },
    { path: "/history", name: "history", component: HistoryPage },
    { path: "/params", name: "params", component: ParamsPage },
    { path: "/ai", name: "ai", component: AIPage },
    { path: "/user", name: "user", component: UserPage },
  ],
});

router.beforeEach((to) => {
  const isPublic = Boolean(to.meta.public);
  const token = getStoredToken();
  if (!isPublic && !token) {
    return { name: "login" };
  }
  if (isPublic && token && to.name === "login") {
    return { name: "overview" };
  }
  return true;
});

export default router;
