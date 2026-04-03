<template>
  <section class="page-section">
    <div class="page-title-row">
      <div>
        <p class="page-eyebrow">Identity</p>
        <h1>User Center</h1>
        <p class="page-intro">
          Keep the authentication story complete without overbuilding a full enterprise RBAC system.
        </p>
      </div>
      <StatusBadge :label="authState.user?.role ?? 'unknown'" tone="primary" />
    </div>

    <PortalCard title="Current User" subtitle="Minimal but complete identity context for the HMI">
      <dl class="description-grid">
        <div><dt>Name</dt><dd>{{ authState.user?.display_name ?? "-" }}</dd></div>
        <div><dt>Username</dt><dd>{{ authState.user?.username ?? "-" }}</dd></div>
        <div><dt>Role</dt><dd>{{ authState.user?.role ?? "-" }}</dd></div>
        <div><dt>Access</dt><dd>{{ authState.user?.role === 'operator' ? 'Monitor and control' : 'Monitor only' }}</dd></div>
      </dl>
      <button class="secondary-button" @click="handleLogout">Sign Out</button>
    </PortalCard>
  </section>
</template>

<script setup lang="ts">
import { useRouter } from "vue-router";

import PortalCard from "../components/PortalCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { useAuth } from "../composables/useAuth";

const router = useRouter();
const { authState, logout } = useAuth();

async function handleLogout() {
  logout();
  await router.push("/login");
}
</script>
