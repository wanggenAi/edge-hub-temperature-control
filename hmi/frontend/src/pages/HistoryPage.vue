<template>
  <section class="page-section">
    <div class="page-title-row page-title-row--compact">
      <div>
        <p class="page-eyebrow">History</p>
        <h1>History Analysis</h1>
      </div>
      <div class="page-title-row__actions">
        <DeviceScopeSelect :model-value="activeDeviceId" @update:model-value="handleDeviceChange" />
      </div>
    </div>

    <section class="focus-stage focus-stage--form">
      <div class="focus-stage__top">
        <div>
          <p class="focus-stage__eyebrow">Device search and trend</p>
          <h2 class="focus-stage__title">{{ selectedDeviceName }}</h2>
        </div>
        <div class="focus-stage__meta">
          <StatusBadge :label="`${deviceTotal} devices`" tone="primary" />
        </div>
      </div>

      <el-table :data="devices" stripe class="devices-table">
        <el-table-column prop="device_id" label="Device ID" min-width="150" />
        <el-table-column prop="name" label="Name" min-width="160" />
        <el-table-column label="Status" min-width="100">
          <template #default="{ row }">
            <StatusBadge :label="row.status" :tone="row.status === 'running' ? 'success' : 'warning'" />
          </template>
        </el-table-column>
        <el-table-column prop="location" label="Location" min-width="130" />
        <el-table-column label="Action" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="chooseDevice(row.device_id)">View History</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          background
          layout="prev, pager, next, total"
          :current-page="page"
          :page-size="pageSize"
          :total="deviceTotal"
          @current-change="changePage"
        />
      </div>
    </section>

    <EchartsLineChart
      v-if="history"
      title="Temperature and Output Trend"
      :series-list="history.series"
      :height="320"
    />

    <div v-if="history" class="summary-strip">
      <span class="summary-chip">
        <strong>Device</strong>
        {{ history.device_id }}
      </span>
      <span class="summary-chip">
        <strong>Range</strong>
        {{ history.range_label }}
      </span>
      <span class="summary-chip">
        <strong>Avg Temp</strong>
        {{ metricValue("avg_temp") }} C
      </span>
      <span class="summary-chip">
        <strong>Max Error</strong>
        {{ metricValue("max_error") }} C
      </span>
      <span class="summary-chip">
        <strong>Avg PWM</strong>
        {{ metricValue("avg_pwm") }}
      </span>
    </div>

    <details v-if="history" class="compact-fold">
      <summary>Run Summaries</summary>
      <div class="compact-fold__body">
        <div class="run-list">
          <article v-for="run in history.runs" :key="run.run_id" class="run-item">
            <header>
              <h3>{{ run.run_id }}</h3>
              <StatusBadge :label="formatFlushReason(run.flush_reason)" tone="neutral" />
            </header>
            <p>{{ formatDateTime(run.window_start) }} - {{ formatDateTime(run.window_end) }}</p>
            <p>Avg {{ run.sensor_temp_avg.toFixed(2) }} C | Max error {{ run.abs_error_max.toFixed(2) }} C</p>
            <p>PWM {{ run.pwm_duty_min }} - {{ run.pwm_duty_max }}</p>
          </article>
        </div>
      </div>
    </details>

    <p v-if="error" class="form-error">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api } from "../api";
import DeviceScopeSelect from "../components/DeviceScopeSelect.vue";
import EchartsLineChart from "../components/EchartsLineChart.vue";
import StatusBadge from "../components/StatusBadge.vue";
import type { DeviceSummary, HistoryResponse } from "../types";

const route = useRoute();
const router = useRouter();

const history = ref<HistoryResponse | null>(null);
const devices = ref<DeviceSummary[]>([]);
const selectedDeviceMeta = ref<DeviceSummary | null>(null);
const error = ref("");
const page = ref(1);
const pageSize = 8;
const deviceTotal = ref(0);
const activeDeviceId = computed(() =>
  route.query.device_id ? String(route.query.device_id) : undefined,
);

const selectedDeviceName = computed(() => {
  const selected = selectedDeviceMeta.value
    ?? devices.value.find((item) => activeDeviceId.value && sameDeviceId(item.device_id, activeDeviceId.value));
  return selected?.name ?? (activeDeviceId.value || "Select Device");
});

onMounted(async () => {
  await loadDevicePage();
  if (!activeDeviceId.value && devices.value.length > 0) {
    await handleDeviceChange(devices.value[0].device_id);
    return;
  }
  if (activeDeviceId.value) {
    await resolveSelectedDevice(activeDeviceId.value);
  }
});

watch(
  activeDeviceId,
  () => {
    if (!activeDeviceId.value) {
      history.value = null;
      selectedDeviceMeta.value = null;
      return;
    }
    void Promise.all([loadHistory(activeDeviceId.value), resolveSelectedDevice(activeDeviceId.value)]);
  },
  { immediate: true },
);

async function loadDevicePage() {
  try {
    const response = await api.getManagedDevices(page.value, pageSize);
    devices.value = response.items;
    deviceTotal.value = response.total;
    const matched = devices.value.find((item) => activeDeviceId.value && sameDeviceId(item.device_id, activeDeviceId.value));
    if (matched) {
      selectedDeviceMeta.value = matched;
    }
    error.value = "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load devices.";
  }
}

async function loadHistory(deviceId: string) {
  try {
    history.value = await api.getHistory(deviceId);
    error.value = "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load history data.";
  }
}

async function chooseDevice(deviceId: string) {
  await handleDeviceChange(deviceId);
}

async function changePage(nextPage: number) {
  page.value = nextPage;
  await loadDevicePage();
}

function metricValue(key: string) {
  return history.value?.kpis.find((metric) => metric.key === key)?.value ?? "-";
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString();
}

function formatFlushReason(value: string) {
  if (value === "window_complete") return "Window";
  if (value === "idle_flush") return "Idle";
  return value;
}

function sameDeviceId(a: string, b: string) {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

async function handleDeviceChange(deviceId: string | undefined) {
  await router.replace({
    path: route.path,
    query: deviceId ? { device_id: deviceId } : {},
  });
}

async function resolveSelectedDevice(deviceId: string) {
  const current = devices.value.find((item) => sameDeviceId(item.device_id, deviceId));
  if (current) {
    selectedDeviceMeta.value = current;
    return;
  }
  const response = await api.getManagedDevices(1, 20, deviceId);
  const matched = response.items.find((item) => sameDeviceId(item.device_id, deviceId));
  selectedDeviceMeta.value = matched ?? null;
}
</script>
