<template>
  <div class="login-page">
    <section class="login-card">
      <div class="login-card__brand">
        <p class="page-eyebrow">EdgeHub HMI</p>
        <h1>Sign In</h1>
        <p class="login-card__subtitle">Intelligent Temperature Control</p>
      </div>

      <form class="login-form" @submit.prevent="handleSubmit">
        <el-input v-model="username" autocomplete="username" placeholder="Username" />
        <el-input v-model="password" type="password" autocomplete="current-password" show-password placeholder="Password" />
        <el-button type="primary" class="primary-button--block" :loading="submitting" native-type="submit">
          {{ submitting ? "Signing in..." : "Sign In" }}
        </el-button>
      </form>

      <div class="summary-strip summary-strip--stack">
        <span class="summary-chip">
          <strong>Admin</strong>
          admin / admin123
        </span>
        <span class="summary-chip">
          <strong>Operator</strong>
          operator / operator123
        </span>
        <span class="summary-chip">
          <strong>Viewer</strong>
          viewer / viewer123
        </span>
      </div>

      <p v-if="error" class="form-error">{{ error }}</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";

import { useAuth } from "../composables/useAuth";

const router = useRouter();
const { login } = useAuth();

const username = ref("operator");
const password = ref("operator123");
const error = ref("");
const submitting = ref(false);

async function handleSubmit() {
  submitting.value = true;
  error.value = "";
  try {
    await login(username.value, password.value);
    await router.push("/");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Login failed.";
  } finally {
    submitting.value = false;
  }
}
</script>
