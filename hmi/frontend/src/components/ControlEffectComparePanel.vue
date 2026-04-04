<template>
  <section class="portal-card compare-panel">
    <div class="portal-card__header">
      <div>
        <h3>{{ title }}</h3>
        <p>{{ compare.event_label }}{{ compare.event_at ? ` · ${formatDateTime(compare.event_at)}` : "" }}</p>
      </div>
      <div class="compare-panel__badges">
        <StatusBadge :label="compare.conclusion.label" :tone="conclusionTone" />
        <StatusBadge :label="compare.comparable ? 'Comparable' : 'Not comparable'" :tone="compare.comparable ? 'success' : 'warning'" />
      </div>
    </div>
    <div class="portal-card__body compare-panel__body">
      <div class="summary-strip summary-strip--inline">
        <span class="summary-chip summary-chip--plain">
          <strong>Baseline</strong>
          {{ formatWindow(compare.baseline_window) }}
        </span>
        <span class="summary-chip summary-chip--plain">
          <strong>After</strong>
          {{ formatWindow(compare.after_window) }}
        </span>
        <span class="summary-chip summary-chip--plain">
          <strong>Flat threshold</strong>
          {{ compare.thresholds.flat_change_pct }}%
        </span>
      </div>

      <p class="compare-panel__summary">{{ compare.conclusion.summary }}</p>
      <p v-if="!compare.comparable && compare.not_comparable_reason" class="compare-panel__reason">
        {{ compare.not_comparable_reason }}
      </p>

      <ul v-if="compare.conclusion.highlights.length" class="compare-panel__highlights">
        <li v-for="highlight in compare.conclusion.highlights" :key="highlight">{{ highlight }}</li>
      </ul>

      <div class="table-shell">
        <table class="data-table compare-table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Baseline</th>
              <th>After</th>
              <th>Change</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="metric in compare.metrics" :key="metric.key">
              <td>
                <strong>{{ metric.label }}</strong>
                <span v-if="metric.not_comparable_reason" class="data-table__sub">{{ metric.not_comparable_reason }}</span>
              </td>
              <td>{{ formatValue(metric.baseline, metric.unit) }}</td>
              <td>{{ formatValue(metric.after, metric.unit) }}</td>
              <td>{{ formatChange(metric.delta, metric.delta_pct, metric.unit) }}</td>
              <td>
                <StatusBadge :label="metric.status_label" :tone="statusTone(metric.status)" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";

import type { ControlCompareMetricStatus, ControlEffectComparison, ControlCompareWindow } from "../types";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps<{
  title: string;
  compare: ControlEffectComparison;
}>();

const conclusionTone = computed(() => {
  if (props.compare.conclusion.status === "major_improvement" || props.compare.conclusion.status === "slight_improvement") {
    return "success" as const;
  }
  if (props.compare.conclusion.status === "degraded") {
    return "danger" as const;
  }
  if (props.compare.conclusion.status === "not_comparable") {
    return "warning" as const;
  }
  return "neutral" as const;
});

function statusTone(status: ControlCompareMetricStatus) {
  if (status === "improved") return "success" as const;
  if (status === "worse") return "danger" as const;
  if (status === "flat") return "neutral" as const;
  return "warning" as const;
}

function formatWindow(window: ControlCompareWindow) {
  return `${window.sample_count} samples | ${window.steady_state_detected ? "steady detected" : "steady not detected"}`;
}

function formatValue(value: number | null | undefined, unit: string) {
  if (value === undefined || value === null) return "-";
  const digits = unit === "s" || unit === "%" ? 1 : 3;
  return `${value.toFixed(digits)} ${unit}`;
}

function formatChange(delta: number | null | undefined, deltaPct: number | null | undefined, unit: string) {
  if (delta === undefined || delta === null) return "-";
  const signed = delta > 0 ? `+${delta.toFixed(unit === "s" || unit === "%" ? 1 : 3)}` : `${delta.toFixed(unit === "s" || unit === "%" ? 1 : 3)}`;
  if (deltaPct === undefined || deltaPct === null) return `${signed} ${unit}`;
  const pct = deltaPct > 0 ? `+${deltaPct.toFixed(1)}` : `${deltaPct.toFixed(1)}`;
  return `${signed} ${unit} (${pct}%)`;
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString([], {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
</script>

