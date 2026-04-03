<template>
  <section class="page-section">
    <div v-if="overview" class="overview-hero">
      <div>
        <p class="page-eyebrow">System Entry Portal</p>
        <h1>{{ overview.hero_title }}</h1>
        <p class="page-intro">{{ overview.hero_description }}</p>
      </div>
      <StatusBadge label="Defense-ready MVP" tone="success" />
    </div>

    <div v-if="overview" class="metric-grid">
      <MetricCard v-for="metric in overview.live_cards" :key="metric.key" :metric="metric" />
    </div>

    <div v-if="overview" class="two-column-grid">
      <PortalCard title="Current Parameter State" subtitle="FastAPI aggregation of active control settings">
        <dl class="description-grid">
          <div><dt>Target</dt><dd>{{ overview.current_parameters.target_temp_c.toFixed(1) }} C</dd></div>
          <div><dt>Kp</dt><dd>{{ overview.current_parameters.kp.toFixed(1) }}</dd></div>
          <div><dt>Ki</dt><dd>{{ overview.current_parameters.ki.toFixed(1) }}</dd></div>
          <div><dt>Kd</dt><dd>{{ overview.current_parameters.kd.toFixed(1) }}</dd></div>
          <div><dt>Period</dt><dd>{{ overview.current_parameters.control_period_ms }} ms</dd></div>
          <div><dt>Mode</dt><dd>{{ overview.current_parameters.control_mode }}</dd></div>
        </dl>
      </PortalCard>

      <PortalCard title="Latest params/ack" subtitle="Control feedback for the most recent parameter transaction">
        <div class="info-stack">
          <p><strong>Status:</strong> {{ overview.recent_ack.success ? "Success" : "Failed" }}</p>
          <p><strong>Type:</strong> {{ overview.recent_ack.ack_type }}</p>
          <p><strong>Time:</strong> {{ formatDateTime(overview.recent_ack.received_at) }}</p>
          <p>{{ overview.recent_ack.reason }}</p>
        </div>
      </PortalCard>
    </div>

    <div v-if="overview" class="two-column-grid">
      <PortalCard title="Latest Run Summary" subtitle="Historical summary prepared for thesis explanation">
        <div class="summary-card">
          <p><strong>Run ID:</strong> {{ overview.latest_summary.run_id }}</p>
          <p><strong>Average Temperature:</strong> {{ overview.latest_summary.sensor_temp_avg.toFixed(2) }} C</p>
          <p><strong>Max Error:</strong> {{ overview.latest_summary.abs_error_max.toFixed(2) }} C</p>
          <p><strong>PWM Range:</strong> {{ overview.latest_summary.pwm_duty_min }} - {{ overview.latest_summary.pwm_duty_max }}</p>
          <p><strong>Duration:</strong> {{ formatDuration(overview.latest_summary.duration_ms) }}</p>
        </div>
      </PortalCard>

      <PortalCard title="System Architecture" subtitle="The full chain that should be easy to explain during defense">
        <ul class="architecture-list">
          <li v-for="node in overview.architecture" :key="node.name">
            <div>
              <strong>{{ node.name }}</strong>
              <p>{{ node.role }}</p>
            </div>
            <StatusBadge :label="node.status" tone="primary" />
          </li>
        </ul>
      </PortalCard>
    </div>

    <PortalCard v-if="overview" title="Quick Access" subtitle="Recommended narrative path for the demonstration">
      <div class="quick-action-grid">
        <RouterLink v-for="item in overview.quick_actions" :key="item.route" :to="item.route" class="quick-action">
          <h3>{{ item.title }}</h3>
          <p>{{ item.description }}</p>
        </RouterLink>
      </div>
    </PortalCard>

    <p v-if="error" class="form-error">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import { api } from "../api";
import MetricCard from "../components/MetricCard.vue";
import PortalCard from "../components/PortalCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import type { OverviewResponse } from "../types";

const overview = ref<OverviewResponse | null>(null);
const error = ref("");

onMounted(async () => {
  try {
    overview.value = await api.getOverview();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load overview.";
  }
});

function formatDateTime(value: string) {
  return new Date(value).toLocaleString();
}

function formatDuration(durationMs: number) {
  const minutes = Math.round(durationMs / 60000);
  return `${minutes} min`;
}
</script>
