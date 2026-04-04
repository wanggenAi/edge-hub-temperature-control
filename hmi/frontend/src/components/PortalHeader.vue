<template>
  <header class="portal-header">
    <div class="portal-header__brand">
      <RouterLink to="/" class="portal-header__title">
        EdgeHub HMI
      </RouterLink>
      <p class="portal-header__subtitle">Intelligent Temperature Control</p>
    </div>

    <nav class="portal-header__nav" aria-label="Primary">
      <RouterLink v-for="item in items" :key="item.key" :to="item.to" class="portal-header__link">
        {{ item.label }}
      </RouterLink>
    </nav>

    <div class="portal-header__user">
      <span class="portal-header__profile">{{ user?.display_name ?? "System Admin" }}</span>
      <el-button text @click="handleLogout">Sign Out</el-button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import { useAuth } from "../composables/useAuth";
import type { UserPublic } from "../types";

const props = defineProps<{
  user: UserPublic | null;
}>();

const router = useRouter();
const route = useRoute();
const { logout } = useAuth();

const items = computed(() => {
  const scopedDeviceId = route.query.device_id ? String(route.query.device_id) : undefined;
  const scopedQuery = scopedDeviceId ? { device_id: scopedDeviceId } : undefined;
  const scopedTo = (path: string) => (scopedQuery ? { path, query: scopedQuery } : path);
  const base = [
    { key: "overview", label: "Overview", to: "/" },
    { key: "realtime", label: "Realtime", to: scopedTo("/realtime") },
    { key: "history", label: "History", to: scopedTo("/history") },
    { key: "params", label: "Params", to: scopedTo("/params") },
    { key: "ai", label: "AI", to: scopedTo("/ai") },
  ];
  if (props.user?.permissions.includes("system.manage")) {
    base.push({ key: "system", label: "System", to: "/system" });
  }
  return base;
});

async function handleLogout() {
  logout();
  await router.push("/login");
}
</script>
