<template>
  <section class="page-section">
    <div class="page-title-row page-title-row--compact">
      <div>
        <p class="page-eyebrow">Overview</p>
        <h1>Device Management</h1>
      </div>
      <div class="page-title-row__actions">
        <DeviceScopeSelect :model-value="activeDeviceId" @update:model-value="handleDeviceChange" />
      </div>
    </div>

    <section class="focus-stage focus-stage--form">
      <div class="focus-stage__top">
        <div>
          <p class="focus-stage__eyebrow">Entry and control</p>
          <h2 class="focus-stage__title">My Device Inventory</h2>
        </div>
        <div class="focus-stage__meta">
          <StatusBadge :label="`${stats.running} running`" tone="success" />
          <StatusBadge :label="`${stats.total} total`" tone="primary" />
        </div>
      </div>

      <div class="summary-strip">
        <span class="summary-chip"><strong>Total</strong>{{ stats.total }}</span>
        <span class="summary-chip"><strong>Running</strong>{{ stats.running }}</span>
        <span class="summary-chip"><strong>Idle</strong>{{ stats.idle }}</span>
        <span class="summary-chip"><strong>Offline</strong>{{ stats.offline }}</span>
      </div>

      <div class="system-toolbar">
        <div>
          <h3 class="system-toolbar__title">Device List</h3>
          <p class="system-toolbar__note">
            {{ canManage ? "Search and manage devices directly from the table." : "Search and open device details." }}
          </p>
        </div>
        <div class="button-row">
          <el-button @click="loadAll">Refresh</el-button>
          <el-button v-if="canManage" type="primary" @click="startCreate">New Device</el-button>
        </div>
      </div>

      <el-table :data="devices" stripe class="devices-table">
        <el-table-column prop="device_id" label="Device ID" min-width="150" />
        <el-table-column prop="name" label="Name" min-width="160" />
        <el-table-column prop="location" label="Location" min-width="120" />
        <el-table-column label="Status" min-width="100">
          <template #default="{ row }">
            <StatusBadge :label="row.status" :tone="row.status === 'running' ? 'success' : 'warning'" />
          </template>
        </el-table-column>
        <el-table-column label="Target" min-width="100">
          <template #default="{ row }">
            {{ row.target_temp_c.toFixed(1) }} C
          </template>
        </el-table-column>
        <el-table-column prop="control_mode" label="Mode" min-width="130" />
        <el-table-column label="Updated" min-width="140">
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="Actions" width="300" fixed="right">
          <template #default="{ row }">
            <el-space>
              <el-button size="small" @click="openDevice(row.device_id)">View</el-button>
              <el-button size="small" @click="openHistory(row.device_id)">History</el-button>
              <el-button v-if="canManage" size="small" @click="startEdit(row.device_id)">Edit</el-button>
              <el-button
                v-if="canManage"
                size="small"
                type="danger"
                plain
                :loading="deletingDeviceId === row.device_id"
                @click="removeDevice(row.device_id)"
              >
                Delete
              </el-button>
            </el-space>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          background
          layout="prev, pager, next, total"
          :current-page="page"
          :page-size="pageSize"
          :total="total"
          @current-change="handlePageChange"
        />
      </div>
    </section>

    <el-drawer
      v-if="canManage"
      v-model="editorVisible"
      :title="creating ? 'Create Device' : `Edit Device: ${form.device_id}`"
      direction="rtl"
      size="420px"
    >
      <el-form label-position="top" class="drawer-form">
        <el-form-item label="Device ID">
          <el-input v-model="form.device_id" :disabled="!creating" placeholder="edge-node-101" />
        </el-form-item>
        <el-form-item label="Name">
          <el-input v-model="form.name" placeholder="Zone 1 Chamber" />
        </el-form-item>
        <el-form-item label="Location">
          <el-input v-model="form.location" placeholder="Lab A" />
        </el-form-item>
        <el-form-item label="Status">
          <el-select v-model="form.status" style="width: 100%">
            <el-option label="running" value="running" />
            <el-option label="idle" value="idle" />
            <el-option label="offline" value="offline" />
          </el-select>
        </el-form-item>
        <el-form-item label="Target Temperature (C)">
          <el-input-number v-model="form.target_temp_c" :min="20" :max="60" :step="0.1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="Control Mode">
          <el-select v-model="form.control_mode" style="width: 100%">
            <el-option label="pi_control" value="pi_control" />
            <el-option label="p_control" value="p_control" />
            <el-option label="manual_hold" value="manual_hold" />
          </el-select>
        </el-form-item>
      </el-form>

      <template #footer>
        <div class="drawer-footer">
          <el-button @click="resetForm">Reset</el-button>
          <el-button @click="editorVisible = false">Cancel</el-button>
          <el-button type="primary" :loading="savingDevice" @click="saveDevice">
            {{ creating ? "Create Device" : "Save Changes" }}
          </el-button>
        </div>
      </template>
    </el-drawer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

import { api } from "../api";
import DeviceScopeSelect from "../components/DeviceScopeSelect.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { useAuth } from "../composables/useAuth";
import type { DeviceSummary } from "../types";

const router = useRouter();
const route = useRoute();
const { authState } = useAuth();

const devices = ref<DeviceSummary[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 10;
const selectedEditorDeviceId = ref<string | null>(null);
const creating = ref(true);
const savingDevice = ref(false);
const deletingDeviceId = ref("");
const editorVisible = ref(false);
const stats = reactive({
  total: 0,
  running: 0,
  idle: 0,
  offline: 0,
});

const form = reactive({
  device_id: "",
  name: "",
  location: "",
  status: "running",
  target_temp_c: 35.0,
  control_mode: "pi_control",
});

const canManage = computed(() => Boolean(authState.user?.permissions.includes("devices.manage")));
const activeDeviceId = computed(() =>
  route.query.device_id ? String(route.query.device_id) : undefined,
);

onMounted(async () => {
  await loadStats();
});

watch(
  activeDeviceId,
  () => {
    page.value = 1;
    void loadDevices();
  },
  { immediate: true },
);

async function loadAll() {
  await Promise.all([loadStats(), loadDevices()]);
}

async function loadStats() {
  const nextStats = await api.getDeviceStats();
  stats.total = nextStats.total;
  stats.running = nextStats.running;
  stats.idle = nextStats.idle;
  stats.offline = nextStats.offline;
}

async function loadDevices() {
  const response = await api.getManagedDevices(page.value, pageSize, activeDeviceId.value);
  devices.value = response.items;
  total.value = response.total;
}

async function handlePageChange(nextPage: number) {
  page.value = nextPage;
  await loadDevices();
}

function startCreate() {
  creating.value = true;
  selectedEditorDeviceId.value = null;
  form.device_id = "";
  form.name = "";
  form.location = "";
  form.status = "running";
  form.target_temp_c = 35.0;
  form.control_mode = "pi_control";
  editorVisible.value = true;
}

function startEdit(deviceId: string) {
  if (!canManage.value) return;
  const found = devices.value.find((device) => device.device_id === deviceId);
  if (!found) return;
  creating.value = false;
  selectedEditorDeviceId.value = deviceId;
  form.device_id = found.device_id;
  form.name = found.name;
  form.location = found.location;
  form.status = found.status;
  form.target_temp_c = Number(found.target_temp_c.toFixed(1));
  form.control_mode = found.control_mode;
  editorVisible.value = true;
}

function resetForm() {
  if (creating.value) {
    startCreate();
    return;
  }
  if (selectedEditorDeviceId.value) {
    startEdit(selectedEditorDeviceId.value);
  }
}

async function saveDevice() {
  if (!canManage.value) return;
  savingDevice.value = true;
  try {
    const payload = {
      device_id: form.device_id.trim(),
      name: form.name.trim(),
      location: form.location.trim(),
      status: form.status,
      target_temp_c: form.target_temp_c,
      control_mode: form.control_mode.trim(),
    };
    if (creating.value) {
      const created = await api.createDevice(payload);
      selectedEditorDeviceId.value = created.device_id;
      ElMessage.success(`Device ${created.device_id} created.`);
    } else {
      const updated = await api.updateDevice(form.device_id, payload);
      ElMessage.success(`Device ${updated.device_id} updated.`);
    }
    editorVisible.value = false;
    await loadAll();
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "Failed to save device.");
  } finally {
    savingDevice.value = false;
  }
}

async function removeDevice(deviceId: string) {
  if (!canManage.value) return;
  try {
    await ElMessageBox.confirm(`Delete device ${deviceId}?`, "Confirm", {
      type: "warning",
      confirmButtonText: "Delete",
      cancelButtonText: "Cancel",
    });
  } catch {
    return;
  }

  deletingDeviceId.value = deviceId;
  try {
    await api.deleteDevice(deviceId);
    ElMessage.success(`Device ${deviceId} deleted.`);
    const nextTotal = total.value - 1;
    const maxPage = Math.max(1, Math.ceil(nextTotal / pageSize));
    if (page.value > maxPage) {
      page.value = maxPage;
    }
    await loadAll();
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "Failed to delete device.");
  } finally {
    deletingDeviceId.value = "";
  }
}

async function openDevice(deviceId: string) {
  await router.push(`/devices/${encodeURIComponent(deviceId)}`);
}

async function openHistory(deviceId: string) {
  await router.push(`/history?device_id=${encodeURIComponent(deviceId)}`);
}

async function handleDeviceChange(deviceId: string | undefined) {
  await router.replace({
    path: route.path,
    query: deviceId ? { device_id: deviceId } : {},
  });
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
