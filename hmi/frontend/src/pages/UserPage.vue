<template>
  <section class="page-section page-section--narrow">
    <div class="page-title-row page-title-row--compact">
      <div>
        <p class="page-eyebrow">User</p>
        <h1>Account</h1>
      </div>
    </div>

    <section class="focus-stage focus-stage--account">
      <div class="focus-stage__top">
        <div>
          <p class="focus-stage__eyebrow">Current session</p>
          <h2 class="focus-stage__title">{{ authState.user?.display_name ?? "-" }}</h2>
        </div>
        <div class="focus-stage__meta">
          <StatusBadge :label="authState.user?.role ?? 'unknown'" tone="primary" />
        </div>
      </div>

      <div class="focus-stage__support">
        <article class="focus-stage__stat">
          <span>Username</span>
          <strong>{{ authState.user?.username ?? "-" }}</strong>
        </article>
        <article class="focus-stage__stat">
          <span>Access</span>
          <strong>{{ authState.user?.role === "operator" ? "Monitor and control" : "Monitor only" }}</strong>
        </article>
      </div>

      <div class="button-row">
        <el-button type="danger" plain @click="handleLogout">Sign Out</el-button>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { useRouter } from "vue-router";

import StatusBadge from "../components/StatusBadge.vue";
import { useAuth } from "../composables/useAuth";

const router = useRouter();
const { authState, logout } = useAuth();

async function handleLogout() {
  logout();
  await router.push("/login");
}
</script>
