<template>
  <PortalCard :title="title" :subtitle="subtitle">
    <div class="chart-shell">
      <svg :viewBox="`0 0 ${width} ${height}`" class="line-chart" role="img" aria-label="trend chart">
        <g>
          <line
            v-for="guide in guides"
            :key="guide"
            :x1="0"
            :x2="width"
            :y1="guide"
            :y2="guide"
            class="line-chart__grid"
          />
        </g>
        <polyline
          v-for="series in normalizedSeries"
          :key="series.name"
          :points="series.path"
          fill="none"
          :stroke="series.color"
          stroke-width="3"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      <div class="chart-meta">
        <div class="chart-meta__legend">
          <span v-for="series in seriesList" :key="series.name" class="chart-meta__item">
            <i :style="{ backgroundColor: series.color }"></i>
            {{ series.name }}
          </span>
        </div>
        <div class="chart-meta__labels">
          <span>{{ startLabel }}</span>
          <span>{{ endLabel }}</span>
        </div>
      </div>
    </div>
  </PortalCard>
</template>

<script setup lang="ts">
import { computed } from "vue";

import type { Series } from "../types";
import PortalCard from "./PortalCard.vue";

const props = withDefaults(
  defineProps<{
    title: string;
    subtitle?: string;
    seriesList: Series[];
    height?: number;
  }>(),
  {
    height: 280,
  },
);

const width = 900;
const height = props.height;

const values = computed(() =>
  props.seriesList.flatMap((series) => series.points.map((point) => point.value)),
);

const minValue = computed(() => Math.min(...values.value));
const maxValue = computed(() => Math.max(...values.value));

const normalizedSeries = computed(() =>
  props.seriesList.map((series) => {
    const step = series.points.length > 1 ? width / (series.points.length - 1) : width;
    const range = Math.max(maxValue.value - minValue.value, 1);
    const path = series.points
      .map((point, index) => {
        const x = index * step;
        const normalized = (point.value - minValue.value) / range;
        const y = height - normalized * (height - 24) - 12;
        return `${x},${y}`;
      })
      .join(" ");
    return {
      ...series,
      path,
    };
  }),
);

const guides = computed(() => [20, height / 2, height - 20]);
const startLabel = computed(() => formatAxis(props.seriesList[0]?.points[0]?.ts));
const endLabel = computed(() => {
  const firstSeries = props.seriesList[0];
  const lastPoint = firstSeries && firstSeries.points.length > 0
    ? firstSeries.points[firstSeries.points.length - 1]
    : undefined;
  return formatAxis(lastPoint?.ts);
});

function formatAxis(value?: string) {
  if (!value) return "";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
</script>
