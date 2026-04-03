<template>
  <div class="login-page">
    <section class="login-page__hero">
      <p class="page-eyebrow">Campus Experimental Portal</p>
      <h1>Intelligent Temperature Control HMI</h1>
      <p class="login-page__text">
        This HMI serves the thesis-defense scenario by clearly separating realtime state,
        historical analysis, parameter closed-loop feedback, and future AI recommendations.
      </p>
      <div class="login-page__demo">
        <div>
          <strong>Demo operator</strong>
          <span>`operator / operator123`</span>
        </div>
        <div>
          <strong>Demo viewer</strong>
          <span>`viewer / viewer123`</span>
        </div>
      </div>
    </section>

    <section class="login-card">
      <h2>Platform Login</h2>
      <p class="login-card__subtitle">Access monitoring, control, and analysis functions.</p>
      <form class="login-form" @submit.prevent="handleSubmit">
        <label>
          Username
          <input v-model="username" autocomplete="username" />
        </label>
        <label>
          Password
          <input v-model="password" type="password" autocomplete="current-password" />
        </label>
        <button class="primary-button" :disabled="submitting">
          {{ submitting ? "Signing in..." : "Sign In" }}
        </button>
      </form>
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
