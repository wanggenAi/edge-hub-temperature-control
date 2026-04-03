<template>
  <section class="chart-panel">
    <header class="chart-panel__header">
      <div>
        <h2 class="chart-panel__title">{{ title }}</h2>
        <p v-if="subtitle" class="chart-panel__subtitle">{{ subtitle }}</p>
      </div>
    </header>
    <div ref="chartRef" class="echarts-shell" :style="{ height: `${height}px` }"></div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import * as echarts from "echarts/core";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { LineChart } from "echarts/charts";
import { CanvasRenderer } from "echarts/renderers";

import type { Series } from "../types";

echarts.use([GridComponent, LegendComponent, TooltipComponent, LineChart, CanvasRenderer]);

const props = withDefaults(
  defineProps<{
    title: string;
    subtitle?: string;
    seriesList: Series[];
    height?: number;
    errorThreshold?: number;
  }>(),
  {
    height: 320,
    errorThreshold: 0.8,
  },
);

const chartRef = ref<HTMLElement | null>(null);
let chart: echarts.ECharts | null = null;

const chartSeries = computed(() => {
  return props.seriesList
    .filter((series) => shouldRenderSeries(series))
    .map((series) => {
      const mapped = mapStyle(series.name);
      return {
        name: series.name,
        type: "line",
        smooth: true,
        showSymbol: false,
        yAxisIndex: mapped.yAxisIndex,
        lineStyle: {
          color: mapped.color,
          width: mapped.width,
          type: mapped.lineType,
        },
        data: series.points.map((point) => [point.ts, Number(point.value.toFixed(3))]),
      };
    });
});

onMounted(async () => {
  await nextTick();
  if (!chartRef.value) return;
  chart = echarts.init(chartRef.value);
  renderChart();
  window.addEventListener("resize", handleResize);
});

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
  chart?.dispose();
  chart = null;
});

watch(
  () => props.seriesList,
  () => {
    renderChart();
  },
  { deep: true },
);

function renderChart() {
  if (!chart) return;
  chart.setOption({
    color: chartSeries.value.map((item) => item.lineStyle.color),
    grid: {
      left: 56,
      right: 56,
      top: 56,
      bottom: 40,
      containLabel: false,
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      backgroundColor: "#ffffff",
      borderColor: "#CBD5E1",
      borderWidth: 1,
      textStyle: { color: "#334155", fontSize: 12 },
    },
    legend: {
      top: 10,
      left: 16,
      icon: "roundRect",
      textStyle: {
        color: "#334155",
        fontSize: 14,
        fontWeight: 400,
      },
    },
    xAxis: {
      type: "time",
      axisLabel: {
        color: "#64748B",
        fontSize: 12,
        fontWeight: 400,
      },
      axisLine: {
        lineStyle: { color: "#E2E8F0" },
      },
      axisTick: { show: false },
      splitLine: { show: false },
    },
    yAxis: [
      {
        type: "value",
        axisLabel: {
          color: "#64748B",
          fontSize: 12,
          fontWeight: 400,
        },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: {
          show: true,
          lineStyle: { color: "#F1F5F9", width: 1 },
        },
      },
      {
        type: "value",
        axisLabel: {
          color: "#64748B",
          fontSize: 12,
          fontWeight: 400,
        },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
      },
    ],
    series: chartSeries.value,
    animation: false,
  });
}

function mapStyle(name: string): { color: string; width: number; lineType: "solid" | "dashed"; yAxisIndex: number } {
  if (name.toLowerCase().includes("target")) {
    return { color: "#2B8C83", width: 1.5, lineType: "dashed", yAxisIndex: 0 };
  }
  if (name.toLowerCase().includes("error") || name.toLowerCase().includes("delta")) {
    return { color: "#D97706", width: 1, lineType: "solid", yAxisIndex: 0 };
  }
  if (name.toLowerCase().includes("pwm")) {
    return { color: "#64748B", width: 1, lineType: "solid", yAxisIndex: 1 };
  }
  return { color: "#124B8F", width: 2, lineType: "solid", yAxisIndex: 0 };
}

function shouldRenderSeries(series: Series): boolean {
  const isErrorSeries =
    series.name.toLowerCase().includes("error") || series.name.toLowerCase().includes("delta");
  if (!isErrorSeries) {
    return true;
  }
  return series.points.some((point) => Math.abs(point.value) > props.errorThreshold);
}

function handleResize() {
  chart?.resize();
}
</script>
