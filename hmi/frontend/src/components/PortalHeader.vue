<template>
  <header class="portal-header">
    <div class="portal-header__brand">
      <p class="portal-header__eyebrow">Application Decision Layer</p>
      <RouterLink to="/" class="portal-header__title">
        Intelligent Temperature Control Experimental Platform
      </RouterLink>
      <p class="portal-header__subtitle">
        FastAPI + Vue HMI for monitoring, parameter control, and thesis demonstration.
      </p>
    </div>

    <nav class="portal-header__nav">
      <RouterLink v-for="item in items" :key="item.to" :to="item.to" class="portal-header__link">
        {{ item.label }}
      </RouterLink>
    </nav>

    <div class="portal-header__user">
      <StatusBadge :label="user?.role === 'operator' ? 'Operator' : 'Viewer'" tone="primary" />
      <RouterLink to="/user" class="portal-header__profile">
        {{ user?.display_name ?? "Guest" }}
      </RouterLink>
    </div>
  </header>
</template>

<script setup lang="ts">
import { RouterLink } from "vue-router";

import type { UserPublic } from "../types";
import StatusBadge from "./StatusBadge.vue";

defineProps<{
  user: UserPublic | null;
}>();

const items = [
  { label: "Overview", to: "/" },
  { label: "Realtime", to: "/realtime" },
  { label: "History", to: "/history" },
  { label: "Parameters", to: "/params" },
  { label: "AI Reserve", to: "/ai" },
];
</script>
