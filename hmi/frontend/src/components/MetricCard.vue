<template>
  <PortalCard>
    <div class="metric-card">
      <p class="metric-card__label">{{ metric.label }}</p>
      <div class="metric-card__value-row">
        <strong class="metric-card__value">{{ metric.value }}</strong>
        <span v-if="metric.unit" class="metric-card__unit">{{ metric.unit }}</span>
      </div>
      <p v-if="metric.trend_hint" class="metric-card__hint">{{ metric.trend_hint }}</p>
      <p class="metric-card__source">{{ sourceLabel(metric.data_source) }}</p>
    </div>
  </PortalCard>
</template>

<script setup lang="ts">
import PortalCard from "./PortalCard.vue";
import type { MetricCard as MetricCardType } from "../types";

defineProps<{
  metric: MetricCardType;
}>();

function sourceLabel(source: MetricCardType["data_source"]) {
  if (source === "realtime_link") return "Realtime chain";
  if (source === "historical_store") return "TDengine history";
  if (source === "ai_reserved") return "AI reserve";
  return "FastAPI aggregate";
}
</script>
