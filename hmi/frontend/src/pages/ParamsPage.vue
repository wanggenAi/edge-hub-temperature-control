<template>
  <section class="page-section">
    <div class="page-title-row">
      <div>
        <p class="page-eyebrow">Parameter State</p>
        <h1>Parameter Management</h1>
        <p class="page-intro">
          Demonstrate the full control loop: parameter viewing, submission, and params/ack feedback.
        </p>
      </div>
      <StatusBadge :label="isOperator ? 'Control enabled' : 'View only'" :tone="isOperator ? 'success' : 'warning'" />
    </div>

    <div v-if="pageData" class="two-column-grid">
      <PortalCard title="Current Active Parameters" subtitle="Latest active control values exposed by the HMI service">
        <dl class="description-grid">
          <div><dt>Target</dt><dd>{{ pageData.current.target_temp_c.toFixed(1) }} C</dd></div>
          <div><dt>Kp</dt><dd>{{ pageData.current.kp.toFixed(1) }}</dd></div>
          <div><dt>Ki</dt><dd>{{ pageData.current.ki.toFixed(1) }}</dd></div>
          <div><dt>Kd</dt><dd>{{ pageData.current.kd.toFixed(1) }}</dd></div>
          <div><dt>Period</dt><dd>{{ pageData.current.control_period_ms }} ms</dd></div>
          <div><dt>Mode</dt><dd>{{ pageData.current.control_mode }}</dd></div>
        </dl>
      </PortalCard>

      <PortalCard title="Latest params/ack" subtitle="Feedback status after the most recent control command">
        <div class="info-stack">
          <p><strong>Status:</strong> {{ pageData.latest_ack.success ? "Success" : "Failed" }}</p>
          <p><strong>Applied immediately:</strong> {{ pageData.latest_ack.applied_immediately ? "Yes" : "No" }}</p>
          <p><strong>Time:</strong> {{ formatDateTime(pageData.latest_ack.received_at) }}</p>
          <p>{{ pageData.latest_ack.reason }}</p>
        </div>
      </PortalCard>
    </div>

    <PortalCard title="Submit Parameter Command" subtitle="Only operator role can issue parameter updates">
      <form class="params-form" @submit.prevent="handleSubmit">
        <label>
          Target Temperature (C)
          <input v-model.number="form.target_temp_c" type="number" step="0.1" :disabled="!isOperator || submitting" />
        </label>
        <label>
          Kp
          <input v-model.number="form.kp" type="number" step="0.1" :disabled="!isOperator || submitting" />
        </label>
        <label>
          Ki
          <input v-model.number="form.ki" type="number" step="0.1" :disabled="!isOperator || submitting" />
        </label>
        <label>
          Kd
          <input v-model.number="form.kd" type="number" step="0.1" :disabled="!isOperator || submitting" />
        </label>
        <label>
          Control Period (ms)
          <input v-model.number="form.control_period_ms" type="number" :disabled="!isOperator || submitting" />
        </label>
        <label>
          Control Mode
          <select v-model="form.control_mode" :disabled="!isOperator || submitting">
            <option value="pi_control">pi_control</option>
            <option value="p_control">p_control</option>
            <option value="manual_hold">manual_hold</option>
          </select>
        </label>
        <button class="primary-button" :disabled="!isOperator || submitting">
          {{ submitting ? "Submitting..." : "Submit Parameters" }}
        </button>
      </form>
      <p v-if="submitMessage" class="form-success">{{ submitMessage }}</p>
    </PortalCard>

    <PortalCard v-if="pageData" title="Recent Ack History" subtitle="Recent transaction trail for the HMI control page">
      <div class="run-list">
        <article v-for="ack in pageData.recent_acks" :key="ack.received_at" class="run-item">
          <header>
            <h3>{{ ack.ack_type }}</h3>
            <StatusBadge :label="ack.success ? 'success' : 'failed'" :tone="ack.success ? 'success' : 'warning'" />
          </header>
          <p>{{ formatDateTime(ack.received_at) }}</p>
          <p>Target {{ ack.target_temp_c.toFixed(1) }} C | Kp {{ ack.kp.toFixed(1) }} | Ki {{ ack.ki.toFixed(1) }}</p>
          <p>{{ ack.reason }}</p>
        </article>
      </div>
    </PortalCard>

    <p v-if="error" class="form-error">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import { api } from "../api";
import PortalCard from "../components/PortalCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { useAuth } from "../composables/useAuth";
import type { ParameterCommandRequest, ParameterPageResponse } from "../types";

const { authState } = useAuth();
const pageData = ref<ParameterPageResponse | null>(null);
const error = ref("");
const submitting = ref(false);
const submitMessage = ref("");
const isOperator = computed(() => authState.user?.role === "operator");

const form = reactive<ParameterCommandRequest>({
  target_temp_c: 35.0,
  kp: 120.0,
  ki: 12.0,
  kd: 0.0,
  control_period_ms: 1000,
  control_mode: "pi_control",
  apply_immediately: true,
});

async function loadPage() {
  try {
    pageData.value = await api.getParameters();
    Object.assign(form, pageData.value.current, { apply_immediately: true });
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load parameter data.";
  }
}

async function handleSubmit() {
  if (!isOperator.value) return;
  submitting.value = true;
  error.value = "";
  submitMessage.value = "";
  try {
    const ack = await api.submitParameters(form);
    submitMessage.value = `Command accepted at ${formatDateTime(ack.received_at)}.`;
    await loadPage();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to submit parameters.";
  } finally {
    submitting.value = false;
  }
}

onMounted(async () => {
  await loadPage();
});

function formatDateTime(value: string) {
  return new Date(value).toLocaleString();
}
</script>
