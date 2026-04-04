<template>
  <el-select
    ref="selectRef"
    :model-value="modelValue"
    filterable
    remote
    clearable
    reserve-keyword
    :placeholder="placeholder"
    :remote-method="remoteSearchDevices"
    :loading="loading"
    class="device-scope-select"
    @change="handleChange"
  >
    <el-option
      v-for="item in options"
      :key="item.device_id"
      :label="`${item.name} (${item.device_id})`"
      :value="item.device_id"
    />
  </el-select>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from "vue";

import { api } from "../api";
import type { DeviceSummary } from "../types";

const props = withDefaults(defineProps<{
  modelValue?: string;
  placeholder?: string;
}>(), {
  placeholder: "Search device id / name",
});

const emit = defineEmits<{
  "update:modelValue": [value: string | undefined];
}>();

const selectRef = ref<{ blur?: () => void } | null>(null);
const options = ref<DeviceSummary[]>([]);
const selectedOption = ref<DeviceSummary | null>(null);
const loading = ref(false);
let searchSeq = 0;

onMounted(async () => {
  await remoteSearchDevices("");
});

watch(
  () => props.modelValue,
  async (nextValue) => {
    if (!nextValue) return;
    if (selectedOption.value && sameDeviceId(selectedOption.value.device_id, nextValue)) return;
    await ensureSelectedLoaded(nextValue);
  },
  { immediate: true },
);

async function remoteSearchDevices(keyword: string) {
  const seq = ++searchSeq;
  loading.value = true;
  try {
    const response = await api.getManagedDevices(1, 30, keyword);
    if (seq !== searchSeq) return;

    const query = keyword.trim().toLowerCase();
    const merged = dedupeDevices(response.items);
    const matched = merged.find((item) => props.modelValue && sameDeviceId(item.device_id, props.modelValue));
    if (matched) {
      selectedOption.value = matched;
    }

    const selected = selectedOption.value;
    const selectedMatchesQuery = selected
      ? `${selected.name} ${selected.device_id}`.toLowerCase().includes(query)
      : false;
    const shouldKeepSelected = !query || selectedMatchesQuery;
    if (selected && shouldKeepSelected && !merged.some((item) => sameDeviceId(item.device_id, selected.device_id))) {
      merged.unshift(selected);
    }
    options.value = dedupeDevices(merged);
  } finally {
    if (seq === searchSeq) {
      loading.value = false;
    }
  }
}

async function ensureSelectedLoaded(deviceId: string) {
  const response = await api.getManagedDevices(1, 30, deviceId);
  const merged = dedupeDevices([...response.items, ...options.value]);
  options.value = merged;
  const matched = merged.find((item) => sameDeviceId(item.device_id, deviceId));
  if (matched) {
    selectedOption.value = matched;
  }
}

async function handleChange(value: string | undefined) {
  if (value) {
    const found = options.value.find((item) => sameDeviceId(item.device_id, value));
    if (found) {
      selectedOption.value = found;
    }
  }
  emit("update:modelValue", value || undefined);
  await nextTick();
  selectRef.value?.blur?.();
}

function sameDeviceId(a: string, b: string) {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

function dedupeDevices(items: DeviceSummary[]) {
  const seen = new Set<string>();
  const result: DeviceSummary[] = [];
  for (const item of items) {
    const key = item.device_id.trim().toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(item);
  }
  return result;
}
</script>
