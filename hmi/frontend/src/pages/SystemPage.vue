<template>
  <section class="page-section">
    <div class="page-title-row page-title-row--compact">
      <div>
        <p class="page-eyebrow">System</p>
        <h1>System Management</h1>
      </div>
    </div>

    <section v-if="access" class="focus-stage focus-stage--form">
      <div class="focus-stage__top">
        <div>
          <p class="focus-stage__eyebrow">Users and access scope</p>
          <h2 class="focus-stage__title">User Management</h2>
        </div>
        <div class="focus-stage__meta">
          <StatusBadge label="JWT secured" tone="success" />
          <StatusBadge label="SQLite RBAC" tone="primary" />
        </div>
      </div>

      <div class="summary-strip">
        <span class="summary-chip"><strong>Users</strong>{{ access.users.length }}</span>
        <span class="summary-chip"><strong>Roles</strong>{{ access.roles.length }}</span>
        <span class="summary-chip"><strong>Devices</strong>{{ access.devices.length }}</span>
        <span class="summary-chip"><strong>Permissions</strong>{{ access.permissions.length }}</span>
      </div>

      <div class="system-toolbar">
        <div>
          <h3 class="system-toolbar__title">Current Users</h3>
          <p class="system-toolbar__note">List-based edit, add, and delete.</p>
        </div>
        <div class="button-row">
          <el-button @click="loadAccess">Refresh</el-button>
          <el-button type="primary" @click="startCreateUser">New User</el-button>
        </div>
      </div>

      <div class="filter-row">
        <el-input
          v-model.trim="userSearch"
          clearable
          placeholder="Search username / display name"
          @keyup.enter="userPage = 1"
        />
        <el-select v-model="roleFilter" clearable placeholder="Role" style="width: 200px">
          <el-option label="All Roles" value="" />
          <el-option v-for="role in access.roles" :key="role.key" :label="role.name" :value="role.key" />
        </el-select>
        <el-button text @click="clearUserFilters">Clear</el-button>
      </div>

      <el-table :data="pagedUsers" stripe class="devices-table">
        <el-table-column prop="username" label="Username" min-width="130" />
        <el-table-column prop="display_name" label="Name" min-width="150" />
        <el-table-column label="Role" min-width="120">
          <template #default="{ row }">
            {{ roleName(row.role) }}
          </template>
        </el-table-column>
        <el-table-column label="Status" min-width="110">
          <template #default="{ row }">
            <StatusBadge :label="row.enabled ? 'enabled' : 'disabled'" :tone="row.enabled ? 'success' : 'warning'" />
          </template>
        </el-table-column>
        <el-table-column label="Device Scope" min-width="120">
          <template #default="{ row }">
            {{ scopeSummary(row.assigned_device_ids, row.role) }}
          </template>
        </el-table-column>
        <el-table-column label="Actions" width="210" fixed="right">
          <template #default="{ row }">
            <el-space>
              <el-button size="small" @click="editUser(row)">Edit</el-button>
              <el-button
                size="small"
                type="danger"
                plain
                :disabled="row.username === 'admin'"
                :loading="deletingUsername === row.username"
                @click="removeUser(row.username)"
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
          :current-page="userPage"
          :page-size="userPageSize"
          :total="filteredUsers.length"
          @current-change="handleUserPageChange"
        />
      </div>
    </section>

    <details v-if="access" class="compact-fold">
      <summary>Role Management</summary>
      <div class="compact-fold__body compact-fold__body--dense">
        <el-table :data="access.roles" stripe class="devices-table">
          <el-table-column prop="name" label="Role" min-width="140" />
          <el-table-column prop="key" label="Key" min-width="130" />
          <el-table-column label="Permissions" min-width="360">
            <template #default="{ row }">
              {{ row.permissions.join(", ") }}
            </template>
          </el-table-column>
        </el-table>

        <form class="system-form" @submit.prevent="saveRole">
          <el-form label-position="top" class="system-form__grid system-form__grid--roles">
            <el-form-item label="Role Key">
              <el-input v-model="roleForm.key" />
            </el-form-item>
            <el-form-item label="Role Name">
              <el-input v-model="roleForm.name" />
            </el-form-item>
          </el-form>

          <div class="permission-block permission-list-field">
            <span>Permissions</span>
            <el-checkbox-group v-model="roleForm.permissions" class="permission-list">
              <el-checkbox v-for="permission in access.permissions" :key="permission.key" :label="permission.key">
                {{ permission.label }}
              </el-checkbox>
            </el-checkbox-group>
          </div>

          <div class="system-form__footer">
            <span class="summary-chip summary-chip--plain">
              <strong>Selected</strong>
              {{ roleForm.permissions.length }}
            </span>
            <el-button type="primary" :loading="savingRole" native-type="submit">Save Role</el-button>
          </div>
        </form>
      </div>
    </details>

    <details v-if="access" class="compact-fold">
      <summary>Device Inventory</summary>
      <div class="compact-fold__body compact-fold__body--dense">
        <div class="filter-row">
          <el-input v-model.trim="deviceSearch" clearable placeholder="Search device id / name" />
          <el-button text @click="deviceSearch = ''">Clear</el-button>
        </div>
        <el-table :data="filteredDevices" stripe class="devices-table">
          <el-table-column prop="device_id" label="Device ID" min-width="150" />
          <el-table-column prop="name" label="Name" min-width="150" />
          <el-table-column prop="location" label="Location" min-width="140" />
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
        </el-table>
      </div>
    </details>

    <el-drawer
      v-if="access"
      v-model="userEditorVisible"
      :title="creatingUser ? 'Create User' : `Edit User: ${userForm.username}`"
      direction="rtl"
      size="460px"
      @closed="resetUserEditor"
    >
      <el-form label-position="top" class="drawer-form">
        <el-form-item label="Username">
          <el-input v-model="userForm.username" :disabled="!creatingUser" placeholder="username" />
        </el-form-item>
        <el-form-item label="Display Name">
          <el-input v-model="userForm.display_name" placeholder="Display name" />
        </el-form-item>
        <el-form-item label="Role">
          <el-select v-model="userForm.role" style="width: 100%" @change="handleRoleChange">
            <el-option v-for="role in access.roles" :key="role.key" :label="role.name" :value="role.key" />
          </el-select>
        </el-form-item>
        <el-form-item label="Password">
          <el-input
            v-model="userForm.password"
            type="password"
            show-password
            :placeholder="creatingUser ? 'Required for new user' : 'Leave blank to keep current password'"
          />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="userForm.enabled">Enabled</el-checkbox>
        </el-form-item>
        <el-form-item label="Assigned Devices">
          <el-select
            v-model="userForm.device_ids"
            multiple
            filterable
            clearable
            collapse-tags
            collapse-tags-tooltip
            reserve-keyword
            :disabled="userForm.role === 'admin'"
            placeholder="Search and assign devices"
            style="width: 100%"
          >
            <el-option
              v-for="device in access.devices"
              :key="device.device_id"
              :label="`${device.name} (${device.device_id})`"
              :value="device.device_id"
            />
          </el-select>
          <p v-if="userForm.role === 'admin'" class="page-intro">Admin role automatically has all devices.</p>
        </el-form-item>
      </el-form>

      <template #footer>
        <div class="drawer-footer">
          <el-button @click="resetUserEditor">Reset</el-button>
          <el-button @click="userEditorVisible = false">Cancel</el-button>
          <el-button type="primary" :loading="savingUser" @click="saveUser">
            {{ creatingUser ? "Create User" : "Save Changes" }}
          </el-button>
        </div>
      </template>
    </el-drawer>

    <p v-if="error" class="form-error">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { api } from "../api";
import StatusBadge from "../components/StatusBadge.vue";
import type { ManagedUser, SystemAccessResponse } from "../types";

const access = ref<SystemAccessResponse | null>(null);
const error = ref("");
const savingUser = ref(false);
const savingRole = ref(false);
const deletingUsername = ref("");
const selectedUsername = ref<string | null>(null);
const creatingUser = ref(false);
const userEditorVisible = ref(false);
const userSearch = ref("");
const roleFilter = ref("");
const deviceSearch = ref("");
const userPage = ref(1);
const userPageSize = 8;

const userForm = reactive({
  username: "",
  display_name: "",
  role: "",
  password: "",
  enabled: true,
  device_ids: [] as string[],
});

const roleForm = reactive({
  key: "qa_viewer",
  name: "QA Viewer",
  permissions: ["overview.view", "realtime.view", "history.view"],
});

const filteredUsers = computed(() => {
  const users = access.value?.users ?? [];
  const keyword = userSearch.value.trim().toLowerCase();
  return users.filter((user) => {
    const matchedKeyword = !keyword
      || user.username.toLowerCase().includes(keyword)
      || user.display_name.toLowerCase().includes(keyword);
    const matchedRole = !roleFilter.value || user.role === roleFilter.value;
    return matchedKeyword && matchedRole;
  });
});

const pagedUsers = computed(() => {
  const start = (userPage.value - 1) * userPageSize;
  return filteredUsers.value.slice(start, start + userPageSize);
});

const filteredDevices = computed(() => {
  const devices = access.value?.devices ?? [];
  const keyword = deviceSearch.value.trim().toLowerCase();
  if (!keyword) return devices;
  return devices.filter((device) =>
    device.device_id.toLowerCase().includes(keyword) || device.name.toLowerCase().includes(keyword),
  );
});

watch(filteredUsers, (nextUsers) => {
  const maxPage = Math.max(1, Math.ceil(nextUsers.length / userPageSize));
  if (userPage.value > maxPage) {
    userPage.value = maxPage;
  }
}, { immediate: true });

watch([userSearch, roleFilter], () => {
  userPage.value = 1;
});

onMounted(async () => {
  await loadAccess();
});

async function loadAccess() {
  try {
    access.value = await api.getSystemAccess();
    error.value = "";
    if (!access.value.roles.some((role) => role.key === roleForm.key) && access.value.roles.length > 0) {
      roleForm.key = access.value.roles[0].key;
      roleForm.name = access.value.roles[0].name;
      roleForm.permissions = [...access.value.roles[0].permissions];
    }
    syncUserEditor();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load system access data.";
  }
}

async function saveUser() {
  const targetUsername = userForm.username.trim();
  if (!targetUsername) {
    error.value = "Username is required.";
    return;
  }
  if (!creatingUser.value && !selectedUsername.value) {
    error.value = "Select a user first.";
    return;
  }
  savingUser.value = true;
  error.value = "";
  try {
    await api.saveUser({
      username: targetUsername,
      display_name: userForm.display_name.trim(),
      role: userForm.role,
      password: userForm.password || undefined,
      enabled: userForm.enabled,
      device_ids: userForm.role === "admin" ? null : userForm.device_ids,
    });
    creatingUser.value = false;
    selectedUsername.value = targetUsername;
    userForm.password = "";
    userEditorVisible.value = false;
    ElMessage.success(`User ${targetUsername} saved.`);
    await loadAccess();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to save user.";
  } finally {
    savingUser.value = false;
  }
}

async function removeUser(username: string) {
  try {
    await ElMessageBox.confirm(`Delete user ${username}?`, "Confirm", {
      type: "warning",
      confirmButtonText: "Delete",
      cancelButtonText: "Cancel",
    });
  } catch {
    return;
  }
  deletingUsername.value = username;
  error.value = "";
  try {
    await api.deleteUser(username);
    if (selectedUsername.value === username) {
      selectedUsername.value = null;
    }
    ElMessage.success(`User ${username} deleted.`);
    await loadAccess();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to delete user.";
  } finally {
    deletingUsername.value = "";
  }
}

async function saveRole() {
  savingRole.value = true;
  error.value = "";
  try {
    await api.saveRole({
      key: roleForm.key,
      name: roleForm.name,
      permissions: roleForm.permissions,
    });
    ElMessage.success(`Role ${roleForm.key} saved.`);
    await loadAccess();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to save role.";
  } finally {
    savingRole.value = false;
  }
}

function startCreateUser() {
  creatingUser.value = true;
  selectedUsername.value = null;
  setCreateUserDefaults();
  userEditorVisible.value = true;
}

function editUser(user: ManagedUser) {
  creatingUser.value = false;
  selectedUsername.value = user.username;
  applyUser(user);
  userEditorVisible.value = true;
}

function resetUserEditor() {
  if (creatingUser.value) {
    setCreateUserDefaults();
    return;
  }
  syncUserEditor();
}

function syncUserEditor() {
  if (!access.value) {
    return;
  }
  if (creatingUser.value) {
    if (!userForm.role && access.value.roles.length > 0) {
      userForm.role = access.value.roles[0].key;
    }
    return;
  }
  const fallbackUser = access.value.users[0];
  const selectedUser = access.value.users.find((user) => user.username === selectedUsername.value) ?? fallbackUser;
  if (!selectedUser) {
    startCreateUser();
    return;
  }
  selectedUsername.value = selectedUser.username;
  applyUser(selectedUser);
}

function applyUser(user: ManagedUser) {
  userForm.username = user.username;
  userForm.display_name = user.display_name;
  userForm.role = user.role;
  userForm.password = "";
  userForm.enabled = user.enabled;
  userForm.device_ids = [...user.assigned_device_ids];
}

function handleRoleChange() {
  if (!access.value) return;
  if (userForm.role === "admin") {
    userForm.device_ids = access.value.devices.map((device) => device.device_id);
  }
}

function roleName(roleKey: string) {
  return access.value?.roles.find((role) => role.key === roleKey)?.name ?? roleKey;
}

function scopeSummary(deviceIds: string[], role: string) {
  if (!access.value) return "0 devices";
  if (role === "admin") return `All (${access.value.devices.length})`;
  return `${deviceIds.length} device${deviceIds.length === 1 ? "" : "s"}`;
}

function handleUserPageChange(nextPage: number) {
  userPage.value = nextPage;
}

function clearUserFilters() {
  userSearch.value = "";
  roleFilter.value = "";
  userPage.value = 1;
}

function setCreateUserDefaults() {
  userForm.username = "";
  userForm.display_name = "";
  userForm.role = access.value?.roles[0]?.key ?? "";
  userForm.password = "";
  userForm.enabled = true;
  userForm.device_ids = [];
}
</script>
