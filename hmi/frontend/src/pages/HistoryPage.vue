<template>
  <section class="page-section">
    <div class="page-title-row">
      <div>
        <p class="page-eyebrow">Historical State</p>
        <h1>History Analysis</h1>
        <p class="page-intro">
          Use TDengine-backed historical curves and summaries to explain system stability and traceability.
        </p>
      </div>
      <StatusBadge v-if="history" :label="history.range_label" tone="primary" />
    </div>

    <div v-if="history" class="metric-grid">
      <MetricCard v-for="metric in history.kpis" :key="metric.key" :metric="metric" />
    </div>

    <SimpleLineChart
      v-if="history"
      title="Historical Trend"
      subtitle="Temperature, target, and PWM within the selected history window"
      :series-list="history.series"
    />

    <PortalCard v-if="history" title="Run Summaries" subtitle="Most suitable historical proof points for the defense">
      <div class="run-list">
        <article v-for="run in history.runs" :key="run.run_id" class="run-item">
          <header>
            <h3>{{ run.run_id }}</h3>
            <StatusBadge :label="run.flush_reason" tone="neutral" />
          </header>
          <p>{{ formatDateTime(run.window_start) }} - {{ formatDateTime(run.window_end) }}</p>
          <p>Average temperature {{ run.sensor_temp_avg.toFixed(2) }} C</p>
          <p>Max error {{ run.abs_error_max.toFixed(2) }} C</p>
          <p>PWM range {{ run.pwm_duty_min }} - {{ run.pwm_duty_max }}</p>
        </article>
      </div>
    </PortalCard>

    <p v-if="error" class="form-error">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";

import { api } from "../api";
import MetricCard from "../components/MetricCard.vue";
import PortalCard from "../components/PortalCard.vue";
import SimpleLineChart from "../components/SimpleLineChart.vue";
import StatusBadge from "../components/StatusBadge.vue";
import type { HistoryResponse } from "../types";

const history = ref<HistoryResponse | null>(null);
const error = ref("");

onMounted(async () => {
  try {
    history.value = await api.getHistory();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load history data.";
  }
});

function formatDateTime(value: string) {
  return new Date(value).toLocaleString();
}
</script>
