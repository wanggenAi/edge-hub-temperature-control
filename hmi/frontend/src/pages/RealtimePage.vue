<template>
  <section class="page-section">
    <div class="page-title-row">
      <div>
        <p class="page-eyebrow">Realtime State</p>
        <h1>Realtime Monitoring</h1>
        <p class="page-intro">
          Focus on the live chain: current telemetry, control mode, and actuator output.
        </p>
      </div>
      <StatusBadge :label="snapshot?.system_state ?? 'loading'" tone="success" />
    </div>

    <div v-if="snapshot" class="metric-grid">
      <MetricCard :metric="{ key: 'sensor', label: 'Measured Temperature', value: snapshot.sensor_temp_c.toFixed(2), unit: 'C', trend_hint: 'Realtime telemetry', data_source: 'realtime_link' }" />
      <MetricCard :metric="{ key: 'target', label: 'Target Temperature', value: snapshot.target_temp_c.toFixed(1), unit: 'C', trend_hint: 'Realtime setpoint', data_source: 'realtime_link' }" />
      <MetricCard :metric="{ key: 'pwm', label: 'PWM Duty', value: String(snapshot.pwm_duty), unit: '', trend_hint: 'Actuator output', data_source: 'realtime_link' }" />
      <MetricCard :metric="{ key: 'mode', label: 'Control Mode', value: snapshot.control_mode, unit: '', trend_hint: 'Current controller strategy', data_source: 'fastapi_aggregate' }" />
    </div>

    <SimpleLineChart
      v-if="series"
      title="Realtime Trend Window"
      subtitle="Current temperature, target temperature, and PWM within the latest observation interval"
      :series-list="series.series"
    />

    <div v-if="snapshot" class="two-column-grid">
      <PortalCard title="Current Control State" subtitle="Live telemetry fields most useful in the defense narrative">
        <dl class="description-grid">
          <div><dt>Device</dt><dd>{{ snapshot.device_id }}</dd></div>
          <div><dt>Controller</dt><dd>{{ snapshot.controller_version }}</dd></div>
          <div><dt>Error</dt><dd>{{ snapshot.error_c.toFixed(3) }} C</dd></div>
          <div><dt>Integral Error</dt><dd>{{ snapshot.integral_error.toFixed(3) }}</dd></div>
          <div><dt>Output</dt><dd>{{ snapshot.control_output.toFixed(2) }}</dd></div>
          <div><dt>Period</dt><dd>{{ snapshot.control_period_ms }} ms</dd></div>
        </dl>
      </PortalCard>

      <PortalCard title="Communication and Parameter State" subtitle="Operational context for the current run">
        <div class="info-stack">
          <p><strong>Collected:</strong> {{ formatDateTime(snapshot.collected_at) }}</p>
          <p><strong>Uptime:</strong> {{ formatDuration(snapshot.uptime_ms) }}</p>
          <p><strong>Pending Params:</strong> {{ snapshot.has_pending_params ? "Yes" : "No" }}</p>
          <p><strong>Kp / Ki / Kd:</strong> {{ snapshot.kp.toFixed(1) }} / {{ snapshot.ki.toFixed(1) }} / {{ snapshot.kd.toFixed(1) }}</p>
        </div>
      </PortalCard>
    </div>

    <p v-if="error" class="form-error">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";

import { api } from "../api";
import MetricCard from "../components/MetricCard.vue";
import PortalCard from "../components/PortalCard.vue";
import SimpleLineChart from "../components/SimpleLineChart.vue";
import StatusBadge from "../components/StatusBadge.vue";
import type { RealtimeSeriesResponse, TelemetrySnapshot } from "../types";

const snapshot = ref<TelemetrySnapshot | null>(null);
const series = ref<RealtimeSeriesResponse | null>(null);
const error = ref("");
let timer: number | null = null;

async function loadRealtime() {
  try {
    const [nextSnapshot, nextSeries] = await Promise.all([
      api.getRealtimeSnapshot(),
      api.getRealtimeSeries(),
    ]);
    snapshot.value = nextSnapshot;
    series.value = nextSeries;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load realtime data.";
  }
}

onMounted(async () => {
  await loadRealtime();
  timer = window.setInterval(() => {
    void loadRealtime();
  }, 5000);
});

onUnmounted(() => {
  if (timer !== null) window.clearInterval(timer);
});

function formatDateTime(value: string) {
  return new Date(value).toLocaleString();
}

function formatDuration(durationMs: number) {
  const minutes = Math.floor(durationMs / 60000);
  return `${minutes} min`;
}
</script>
