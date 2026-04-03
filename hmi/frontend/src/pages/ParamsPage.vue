<template>
  <section class="page-section">
    <div class="page-title-row page-title-row--compact">
      <div>
        <p class="page-eyebrow">Parameters</p>
        <h1>Parameter Management</h1>
      </div>
      <div class="page-title-row__actions">
        <DeviceScopeSelect :model-value="activeDeviceId" @update:model-value="handleDeviceChange" />
      </div>
    </div>

    <section v-if="pageData" class="focus-stage focus-stage--form">
      <div class="focus-stage__top">
        <div>
          <p class="focus-stage__eyebrow">Parameter update and ack</p>
          <h2 class="focus-stage__title">{{ pageData.latest_ack.success ? "Latest update confirmed" : "Waiting for confirmation" }}</h2>
        </div>
        <div class="focus-stage__meta">
          <el-button
            v-if="isOperator"
            type="primary"
            :loading="submitting"
            @click="handleSubmit"
          >
            {{ submitting ? "Submitting..." : "Submit Parameters" }}
          </el-button>
          <StatusBadge :label="isOperator ? 'Control enabled' : 'View only'" :tone="isOperator ? 'success' : 'warning'" />
          <StatusBadge :label="pageData.latest_ack.success ? 'Ack success' : 'Ack failed'" :tone="pageData.latest_ack.success ? 'success' : 'danger'" />
        </div>
      </div>

      <div class="focus-stage__support focus-stage__support--wide">
        <article class="focus-stage__stat">
          <span>Target</span>
          <strong>{{ pageData.current.target_temp_c.toFixed(1) }} C</strong>
        </article>
        <article class="focus-stage__stat">
          <span>Kp / Ki / Kd</span>
          <strong>{{ pageData.current.kp.toFixed(1) }} / {{ pageData.current.ki.toFixed(1) }} / {{ pageData.current.kd.toFixed(1) }}</strong>
        </article>
        <article class="focus-stage__stat">
          <span>Mode</span>
          <strong>{{ pageData.current.control_mode }}</strong>
        </article>
        <article class="focus-stage__stat">
          <span>Applied</span>
          <strong>{{ pageData.latest_ack.applied_immediately ? "Yes" : "No" }}</strong>
        </article>
      </div>

      <el-form label-position="top" class="params-form params-form--single">
        <el-form-item label="Target Temperature (C)">
          <el-input-number v-model="form.target_temp_c" :step="0.1" :disabled="!isOperator || submitting" style="width: 100%" />
        </el-form-item>
        <el-form-item label="Kp">
          <el-input-number v-model="form.kp" :step="0.1" :disabled="!isOperator || submitting" style="width: 100%" />
        </el-form-item>
        <el-form-item label="Ki">
          <el-input-number v-model="form.ki" :step="0.1" :disabled="!isOperator || submitting" style="width: 100%" />
        </el-form-item>
        <el-form-item label="Kd">
          <el-input-number v-model="form.kd" :step="0.1" :disabled="!isOperator || submitting" style="width: 100%" />
        </el-form-item>
        <el-form-item label="Control Period (ms)">
          <el-input-number v-model="form.control_period_ms" :step="100" :disabled="!isOperator || submitting" style="width: 100%" />
        </el-form-item>
        <el-form-item label="Control Mode">
          <el-select v-model="form.control_mode" :disabled="!isOperator || submitting" style="width: 100%">
            <el-option label="pi_control" value="pi_control" />
            <el-option label="p_control" value="p_control" />
            <el-option label="manual_hold" value="manual_hold" />
          </el-select>
        </el-form-item>
      </el-form>

      <div class="ack-feedback">
        <p class="ack-feedback__title">Latest ack</p>
        <p class="ack-feedback__line">{{ pageData.latest_ack.reason }}</p>
        <p class="ack-feedback__line">Received {{ formatDateTime(pageData.latest_ack.received_at) }}</p>
        <p v-if="submitMessage" class="form-success">{{ submitMessage }}</p>
      </div>
    </section>

    <div v-if="pageData" class="summary-strip">
      <span class="summary-chip">
        <strong>Device</strong>
        {{ pageData.device_id }}
      </span>
      <span class="summary-chip">
        <strong>Updated</strong>
        {{ formatDateTime(pageData.current.updated_at) }}
      </span>
      <span class="summary-chip">
        <strong>Mode</strong>
        {{ pageData.current.control_mode }}
      </span>
      <span class="summary-chip">
        <strong>Status</strong>
        {{ pageData.latest_ack.applied_immediately ? "Applied" : "Pending" }}
      </span>
    </div>

    <details v-if="pageData" class="compact-fold">
      <summary>Recent Ack History</summary>
      <div class="compact-fold__body">
        <div class="run-list">
          <article v-for="ack in pageData.recent_acks" :key="ack.received_at" class="run-item">
            <header>
              <h3>{{ formatDateTime(ack.received_at) }}</h3>
              <StatusBadge :label="ack.success ? 'success' : 'failed'" :tone="ack.success ? 'success' : 'danger'" />
            </header>
            <p>Target {{ ack.target_temp_c.toFixed(1) }} C | Kp {{ ack.kp.toFixed(1) }} | Ki {{ ack.ki.toFixed(1) }}</p>
            <p>{{ ack.reason }}</p>
          </article>
        </div>
      </div>
    </details>

    <p v-if="error" class="form-error">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api } from "../api";
import DeviceScopeSelect from "../components/DeviceScopeSelect.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { useAuth } from "../composables/useAuth";
import type { ParameterCommandRequest, ParameterPageResponse } from "../types";

const { authState } = useAuth();
const route = useRoute();
const router = useRouter();
const pageData = ref<ParameterPageResponse | null>(null);
const error = ref("");
const submitting = ref(false);
const submitMessage = ref("");
const isOperator = computed(() => Boolean(authState.user?.permissions.includes("params.write")));
const selectedDeviceId = computed(() =>
  route.query.device_id ? String(route.query.device_id) : undefined,
);
const activeDeviceId = computed(() => selectedDeviceId.value ?? pageData.value?.device_id);

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
    pageData.value = await api.getParameters(selectedDeviceId.value);
    Object.assign(form, pageData.value.current, { apply_immediately: true });
    error.value = "";
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
    const ack = await api.submitParameters({
      ...form,
      device_id: selectedDeviceId.value ?? pageData.value?.device_id,
    });
    submitMessage.value = `Command accepted at ${formatDateTime(ack.received_at)}.`;
    await loadPage();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to submit parameters.";
  } finally {
    submitting.value = false;
  }
}

watch(
  selectedDeviceId,
  () => {
    void loadPage();
  },
  { immediate: true },
);

function formatDateTime(value: string) {
  return new Date(value).toLocaleString([], {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function handleDeviceChange(deviceId: string | undefined) {
  await router.replace({
    path: route.path,
    query: deviceId ? { device_id: deviceId } : {},
  });
}
</script>
