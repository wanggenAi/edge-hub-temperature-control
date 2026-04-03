<template>
  <section class="page-section">
    <div class="page-title-row">
      <div>
        <p class="page-eyebrow">AI Reserve</p>
        <h1>AI Suggestions and Intelligent Analysis</h1>
        <p class="page-intro">
          This page reserves the upper-layer decision space for future tuning advice, anomaly analysis,
          and interpretive recommendations.
        </p>
      </div>
      <StatusBadge label="Reserved capability" tone="neutral" />
    </div>

    <PortalCard title="Current Positioning" subtitle="What this page means in the thesis-defense narrative">
      <div class="info-stack">
        <p>The current HMI separates direct control from advisory intelligence.</p>
        <p>AI outputs should be presented as recommendations, not immediate device commands.</p>
        <p>This page demonstrates extension readiness without overbuilding the current stage.</p>
      </div>
    </PortalCard>

    <div v-if="recommendations.length" class="quick-action-grid">
      <PortalCard v-for="item in recommendations" :key="item.title" :title="item.title" :subtitle="item.category">
        <div class="info-stack">
          <p>{{ item.summary }}</p>
          <p><strong>Reason:</strong> {{ item.reason }}</p>
          <p><strong>Confidence:</strong> {{ (item.confidence * 100).toFixed(0) }}%</p>
          <p v-if="item.suggested_kp !== undefined">
            <strong>Suggested PID:</strong>
            {{ item.suggested_kp ?? "-" }} / {{ item.suggested_ki ?? "-" }} / {{ item.suggested_kd ?? "-" }}
          </p>
        </div>
      </PortalCard>
    </div>

    <p v-if="error" class="form-error">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";

import { api } from "../api";
import PortalCard from "../components/PortalCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import type { AIRecommendation } from "../types";

const recommendations = ref<AIRecommendation[]>([]);
const error = ref("");

onMounted(async () => {
  try {
    recommendations.value = await api.getRecommendations();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load AI recommendations.";
  }
});
</script>
