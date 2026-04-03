<template>
  <span class="status-badge" :class="`status-badge--${tone}`">{{ label }}</span>
</template>

<script setup lang="ts">
defineProps<{
  label: string;
  tone?: "primary" | "success" | "warning" | "neutral";
}>();
</script>
