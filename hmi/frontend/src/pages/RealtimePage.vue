<template>
  <section class="page-section">
    <div class="page-title-row page-title-row--compact">
      <div>
        <p class="page-eyebrow">Realtime</p>
        <h1>Realtime Monitoring</h1>
      </div>
      <div class="page-title-row__actions">
        <DeviceScopeSelect :model-value="activeDeviceId" @update:model-value="handleDeviceChange" />
      </div>
    </div>

    <section v-if="snapshot" class="focus-stage">
      <div class="focus-stage__top">
        <div>
          <p class="focus-stage__eyebrow">Current running detail</p>
          <h2 class="focus-stage__title">{{ runLabel }}</h2>
        </div>
        <div class="focus-stage__meta">
          <StatusBadge :label="runLabel" :tone="runTone" />
          <StatusBadge :label="alertLabel" :tone="alertTone" />
        </div>
      </div>

      <div class="focus-stage__lead">
        <div class="focus-stage__value-block">
          <p class="focus-stage__label">Current Temperature</p>
          <strong class="focus-stage__value">{{ snapshot.sensor_temp_c.toFixed(2) }} C</strong>
          <p class="focus-stage__note">Updated {{ formatDateTime(snapshot.collected_at) }}</p>
        </div>

        <div class="focus-stage__support">
          <article class="focus-stage__stat">
            <span>Target</span>
            <strong>{{ snapshot.target_temp_c.toFixed(1) }} C</strong>
          </article>
          <article class="focus-stage__stat">
            <span>Delta</span>
            <strong>{{ Math.abs(snapshot.error_c).toFixed(2) }} C</strong>
          </article>
          <article class="focus-stage__stat">
            <span>PWM</span>
            <strong>{{ snapshot.pwm_duty }}</strong>
          </article>
          <article class="focus-stage__stat">
            <span>Mode</span>
            <strong>{{ snapshot.control_mode }}</strong>
          </article>
        </div>
      </div>
    </section>

    <div v-if="snapshot" class="summary-strip">
      <span class="summary-chip">
        <strong>Device</strong>
        {{ snapshot.device_id }}
      </span>
      <span class="summary-chip">
        <strong>Stable</strong>
        {{ stableLabel }}
      </span>
      <span class="summary-chip">
        <strong>PID</strong>
        {{ snapshot.kp.toFixed(1) }} / {{ snapshot.ki.toFixed(1) }} / {{ snapshot.kd.toFixed(1) }}
      </span>
      <span class="summary-chip">
        <strong>Pending</strong>
        {{ snapshot.has_pending_params ? "Yes" : "No" }}
      </span>
    </div>

    <EchartsLineChart
      v-if="series"
      title="Realtime Trend"
      :series-list="chartSeries"
    />

    <EchartsLineChart
      v-if="series"
      title="Steady-state Error"
      subtitle="Rolling steady error with target band and alert threshold"
      :series-list="[series.steady_error_series]"
      :y-axis-min="0"
      :y-axis-max="steadyErrorAxisMax"
      :threshold-lines="steadyErrorThresholds"
      :force-render-error-series="true"
      :height="260"
    />

    <PortalCard v-if="snapshot" title="Current Context">
      <dl class="description-grid description-grid--compact">
        <div><dt>Device</dt><dd>{{ snapshot.device_id }}</dd></div>
        <div><dt>Controller</dt><dd>{{ snapshot.controller_version }}</dd></div>
        <div><dt>Period</dt><dd>{{ snapshot.control_period_ms }} ms</dd></div>
        <div><dt>Output</dt><dd>{{ snapshot.control_output.toFixed(2) }}</dd></div>
      </dl>
    </PortalCard>

    <p v-if="error" class="form-error">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api } from "../api";
import DeviceScopeSelect from "../components/DeviceScopeSelect.vue";
import EchartsLineChart from "../components/EchartsLineChart.vue";
import PortalCard from "../components/PortalCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import type { RealtimeSeriesResponse, Series, TelemetrySnapshot } from "../types";

type BadgeTone = "primary" | "success" | "warning" | "danger" | "neutral";

const snapshot = ref<TelemetrySnapshot | null>(null);
const series = ref<RealtimeSeriesResponse | null>(null);
const error = ref("");
let timer: number | null = null;
const route = useRoute();
const router = useRouter();

const selectedDeviceId = computed(() =>
  route.query.device_id ? String(route.query.device_id) : undefined,
);
const activeDeviceId = computed(() => selectedDeviceId.value ?? snapshot.value?.device_id);

async function loadRealtime() {
  try {
    const [nextSnapshot, nextSeries] = await Promise.all([
      api.getRealtimeSnapshot(selectedDeviceId.value),
      api.getRealtimeSeries(selectedDeviceId.value),
    ]);
    snapshot.value = nextSnapshot;
    series.value = nextSeries;
    error.value = "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load realtime data.";
  }
}

onMounted(() => {
  timer = window.setInterval(() => {
    void loadRealtime();
  }, 5000);
});

watch(
  selectedDeviceId,
  () => {
    void loadRealtime();
  },
  { immediate: true },
);

onUnmounted(() => {
  if (timer !== null) window.clearInterval(timer);
});

const runLabel = computed(() => snapshot.value?.system_state === "running" ? "Running" : "Waiting");
const runTone = computed<BadgeTone>(() => snapshot.value?.system_state === "running" ? "success" : "warning");
const stableLabel = computed(() => Math.abs(snapshot.value?.error_c ?? 0) <= 0.5 ? "Yes" : "Adjusting");
const alertLabel = computed(() => {
  if (!snapshot.value) return "Loading";
  if (snapshot.value.has_pending_params) return "Pending params";
  if (Math.abs(snapshot.value.error_c) > 1) return "Tracking deviation";
  return "Normal";
});
const alertTone = computed<BadgeTone>(() => {
  if (alertLabel.value === "Normal") return "success";
  if (alertLabel.value === "Loading") return "neutral";
  return "warning";
});

const chartSeries = computed<Series[]>(() => {
  if (!series.value) {
    return [];
  }
  const temperature = series.value.series.find((item) => item.name.toLowerCase().includes("temperature"));
  const target = series.value.series.find((item) => item.name.toLowerCase().includes("target"));
  if (!temperature || !target || temperature.points.length !== target.points.length) {
    return series.value.series;
  }
  const delta: Series = {
    name: "Delta",
    color: "#D97706",
    unit: "C",
    data_source: "fastapi_aggregate",
    points: temperature.points.map((point, index) => ({
      ts: point.ts,
      value: Number((target.points[index].value - point.value).toFixed(3)),
    })),
  };
  return [...series.value.series, delta];
});

const steadyErrorAxisMax = computed(() => {
  const axis = series.value?.goals.realtime_steady_error_axis_c ?? 1.2;
  const floor = (series.value?.goals.target_band_c ?? 0.3) * 2;
  return Math.max(axis, floor);
});

const steadyErrorThresholds = computed(() => {
  if (!series.value) return [];
  const band = series.value.goals.target_band_c;
  const alert = Math.min(steadyErrorAxisMax.value, band * 2);
  return [
    { value: band, label: `Target band ${band.toFixed(2)}C`, color: "#2B8C83", lineType: "dashed" as const },
    { value: alert, label: `Alert ${alert.toFixed(2)}C`, color: "#D97706", lineType: "solid" as const },
  ];
});

function formatDateTime(value: string) {
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

async function handleDeviceChange(deviceId: string | undefined) {
  await router.replace({
    path: route.path,
    query: deviceId ? { device_id: deviceId } : {},
  });
}
</script>
