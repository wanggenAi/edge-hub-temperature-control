<template>
  <section class="page-section">
    <div class="page-title-row page-title-row--compact">
      <div>
        <p class="page-eyebrow">AI</p>
        <h1>AI Suggestions</h1>
      </div>
    </div>

    <section v-if="primaryRecommendation" class="focus-stage focus-stage--advice">
      <div class="focus-stage__top">
        <div>
          <p class="focus-stage__eyebrow">Suggestion and rationale</p>
          <h2 class="focus-stage__title">{{ primaryRecommendation.title }}</h2>
        </div>
        <div class="focus-stage__meta">
          <el-button @click="openParams">Open Params</el-button>
          <StatusBadge :label="recommendationStatus" tone="primary" />
          <StatusBadge :label="`${Math.round(primaryRecommendation.confidence * 100)}% confidence`" tone="neutral" />
        </div>
      </div>

      <div class="focus-stage__support focus-stage__support--wide">
        <article class="focus-stage__stat">
          <span>Recommended Kp</span>
          <strong>{{ formatNullable(primaryRecommendation.suggested_kp) }}</strong>
        </article>
        <article class="focus-stage__stat">
          <span>Recommended Ki</span>
          <strong>{{ formatNullable(primaryRecommendation.suggested_ki) }}</strong>
        </article>
        <article class="focus-stage__stat">
          <span>Recommended Kd</span>
          <strong>{{ formatNullable(primaryRecommendation.suggested_kd) }}</strong>
        </article>
        <article class="focus-stage__stat">
          <span>Current PID</span>
          <strong>{{ currentPid }}</strong>
        </article>
      </div>

      <div class="portal-card">
        <div class="portal-card__body focus-stage__narrative">
          <p class="focus-stage__narrative-title">Reason</p>
          <p>{{ primaryRecommendation.reason }}</p>
          <p class="focus-stage__narrative-title">Direction</p>
          <p>{{ primaryRecommendation.summary }}</p>
        </div>
      </div>
    </section>

    <ControlEffectComparePanel
      v-if="pageData"
      title="Before / After AI Adoption Effect"
      :compare="pageData.adoption_compare"
    />

    <div v-if="parameters" class="summary-strip">
      <span class="summary-chip">
        <strong>Device</strong>
        {{ parameters.device_id }}
      </span>
      <span class="summary-chip">
        <strong>Target</strong>
        {{ parameters.current.target_temp_c.toFixed(1) }} C
      </span>
      <span class="summary-chip">
        <strong>Mode</strong>
        {{ parameters.current.control_mode }}
      </span>
      <span class="summary-chip">
        <strong>Current PID</strong>
        {{ currentPid }}
      </span>
    </div>

    <details v-if="secondaryRecommendations.length" class="compact-fold">
      <summary>More Suggestions</summary>
      <div class="compact-fold__body">
        <div class="run-list">
          <article v-for="item in secondaryRecommendations" :key="item.title" class="run-item">
            <header>
              <h3>{{ item.title }}</h3>
              <StatusBadge :label="`${Math.round(item.confidence * 100)}%`" tone="neutral" />
            </header>
            <p>{{ item.summary }}</p>
            <p>{{ item.reason }}</p>
          </article>
        </div>
      </div>
    </details>

    <p v-if="error" class="form-error">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api } from "../api";
import ControlEffectComparePanel from "../components/ControlEffectComparePanel.vue";
import StatusBadge from "../components/StatusBadge.vue";
import type { AIPageResponse, AIRecommendation, ParameterPageResponse } from "../types";

const pageData = ref<AIPageResponse | null>(null);
const parameters = ref<ParameterPageResponse | null>(null);
const error = ref("");
const route = useRoute();
const router = useRouter();
const selectedDeviceId = computed(() =>
  route.query.device_id ? String(route.query.device_id) : undefined,
);

async function loadPage() {
  try {
    const [nextPageData, nextParameters] = await Promise.all([
      api.getRecommendations(selectedDeviceId.value),
      api.getParameters(selectedDeviceId.value),
    ]);
    pageData.value = nextPageData;
    parameters.value = nextParameters;
    error.value = "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load AI recommendations.";
  }
}

watch(
  selectedDeviceId,
  () => {
    void loadPage();
  },
  { immediate: true },
);

const recommendations = computed<AIRecommendation[]>(() => pageData.value?.recommendations ?? []);
const primaryRecommendation = computed(() => recommendations.value[0] ?? null);
const secondaryRecommendations = computed(() => recommendations.value.slice(1));
const recommendationStatus = computed(() => {
  const status = primaryRecommendation.value?.status ?? "advisory";
  return status.charAt(0).toUpperCase() + status.slice(1);
});
const currentPid = computed(() => {
  if (!parameters.value) return "-";
  const { kp, ki, kd } = parameters.value.current;
  return `${kp.toFixed(1)} / ${ki.toFixed(1)} / ${kd.toFixed(1)}`;
});
const paramsLink = computed(() =>
  selectedDeviceId.value ? `/params?device_id=${encodeURIComponent(selectedDeviceId.value)}` : "/params",
);

async function openParams() {
  await router.push(paramsLink.value);
}

function formatNullable(value?: number | null) {
  return value === undefined || value === null ? "-" : value.toFixed(1);
}
</script>
