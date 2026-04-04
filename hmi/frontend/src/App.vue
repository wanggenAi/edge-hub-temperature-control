<template>
  <div class="app-shell">
    <template v-if="route.name === 'login'">
      <RouterView />
    </template>
    <template v-else>
      <PortalHeader :user="authState.user" />
      <main class="app-main">
        <RouterView />
      </main>
    </template>
  </div>
</template>

<script setup lang="ts">
import { RouterView, useRoute } from "vue-router";

import PortalHeader from "./components/PortalHeader.vue";
import { useAuth } from "./composables/useAuth";

const route = useRoute();
const { authState } = useAuth();
</script>
