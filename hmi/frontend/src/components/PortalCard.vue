<template>
  <section class="portal-card">
    <header v-if="title || subtitle" class="portal-card__header">
      <div>
        <h3 v-if="title">{{ title }}</h3>
        <p v-if="subtitle">{{ subtitle }}</p>
      </div>
      <slot name="header-extra" />
    </header>
    <div class="portal-card__body">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  title?: string;
  subtitle?: string;
}>();
</script>
