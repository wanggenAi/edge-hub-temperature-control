<template>
  <section class="page-section">
    <div class="page-title-row page-title-row--compact">
      <div>
        <p class="page-eyebrow">Device</p>
        <h1>Device Detail</h1>
      </div>
      <div class="button-row button-row--nav">
        <el-button text @click="goToDeviceList">Back to List</el-button>
        <el-button-group>
          <el-button @click="goToScoped('/realtime')">Realtime</el-button>
          <el-button @click="goToScoped('/history')">History</el-button>
          <el-button @click="goToScoped('/params')">Params</el-button>
          <el-button @click="goToScoped('/ai')">AI</el-button>
        </el-button-group>
      </div>
    </div>

    <section v-if="overview" class="overview-stage">
      <div class="overview-stage__header">
        <div>
          <p class="overview-stage__eyebrow">Current running state</p>
          <h2 class="overview-stage__title">{{ overview.selected_device.name }}</h2>
          <p class="overview-stage__device">
            {{ overview.selected_device.device_id }}
            <span>{{ overview.selected_device.location }}</span>
          </p>
        </div>

        <div class="overview-stage__badges">
          <StatusBadge :label="stateLabel" :tone="stateTone" />
          <StatusBadge :label="alertLabel" :tone="alertTone" />
        </div>
      </div>

      <div class="overview-stage__body">
        <div class="overview-stage__primary">
          <p class="overview-stage__metric-label">Current Temperature</p>
          <div class="overview-stage__metric-row">
            <strong class="overview-stage__metric">{{ currentTemp.toFixed(2) }}</strong>
            <span class="overview-stage__unit">C</span>
          </div>
          <div class="overview-stage__secondary">
            <span>
              Telemetry
              <strong>{{ formatDateTime(overview.telemetry_collected_at) }}</strong>
            </span>
            <span>
              Last run
              <strong>{{ overview.latest_summary.run_id }}</strong>
            </span>
          </div>
        </div>

        <div class="overview-stage__stats">
          <article class="overview-stage__stat">
            <span>Target</span>
            <strong>{{ overview.current_parameters.target_temp_c.toFixed(1) }} C</strong>
          </article>
          <article class="overview-stage__stat">
            <span>Delta</span>
            <strong>{{ Math.abs(deltaTemp).toFixed(2) }} C</strong>
          </article>
          <article class="overview-stage__stat">
            <span>PWM</span>
            <strong>{{ pwmValue }}</strong>
          </article>
          <article class="overview-stage__stat">
            <span>Mode</span>
            <strong>{{ overview.current_parameters.control_mode }}</strong>
          </article>
        </div>
      </div>

      <div class="overview-stage__summary">
        <span class="summary-chip">
          <strong>Ack</strong>
          {{ overview.recent_ack.success ? "Success" : "Failed" }}
        </span>
        <span class="summary-chip">
          <strong>Params</strong>
          {{ formatDateTime(overview.current_parameters.updated_at) }}
        </span>
        <span class="summary-chip">
          <strong>Ack time</strong>
          {{ formatDateTime(overview.recent_ack.received_at) }}
        </span>
      </div>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api } from "../api";
import StatusBadge from "../components/StatusBadge.vue";
import type { OverviewResponse } from "../types";

type BadgeTone = "primary" | "success" | "warning" | "danger" | "neutral";

const route = useRoute();
const router = useRouter();
const deviceId = computed(() => String(route.params.deviceId ?? ""));
const overview = ref<OverviewResponse | null>(null);
const error = ref("");

onMounted(async () => {
  await loadOverview();
});

watch(deviceId, async () => {
  await loadOverview();
});

const currentTemp = computed(() => {
  const card = overview.value?.live_cards.find((item) => item.key === "current_temp");
  return Number(card?.value ?? 0);
});

const pwmValue = computed(() => {
  const card = overview.value?.live_cards.find((item) => item.key === "pwm");
  return card?.value ?? "--";
});

const deltaTemp = computed(() => currentTemp.value - (overview.value?.current_parameters.target_temp_c ?? 0));

const stateLabel = computed(() => {
  const status = overview.value?.selected_device.status ?? "";
  return status === "running" || status === "online" ? "Online" : "Idle";
});

const stateTone = computed<BadgeTone>(() => stateLabel.value === "Online" ? "success" : "warning");

const alertLabel = computed(() => {
  if (!overview.value) return "Loading";
  if (!overview.value.recent_ack.success) return "Ack issue";
  if (Math.abs(deltaTemp.value) > 1) return "Tracking";
  return "Normal";
});

const alertTone = computed<BadgeTone>(() => {
  if (alertLabel.value === "Normal") return "success";
  if (alertLabel.value === "Loading") return "neutral";
  return alertLabel.value === "Ack issue" ? "danger" : "warning";
});

function formatDateTime(value: string) {
  return new Date(value).toLocaleString([], {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function loadOverview() {
  try {
    overview.value = await api.getOverview(deviceId.value);
    error.value = "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load device detail.";
  }
}

async function goToDeviceList() {
  await router.push("/");
}

async function goToScoped(path: string) {
  await router.push(`${path}?device_id=${encodeURIComponent(deviceId.value)}`);
}
</script>
