import { computed, reactive } from "vue";

import { api } from "../api";
import type { LoginResponse, UserPublic } from "../types";

const TOKEN_KEY = "edgehub_hmi_token";

const authState = reactive<{
  token: string | null;
  user: UserPublic | null;
  initialized: boolean;
}>({
  token: localStorage.getItem(TOKEN_KEY),
  user: null,
  initialized: false,
});

function applyLogin(response: LoginResponse) {
  authState.token = response.access_token;
  authState.user = response.user;
  localStorage.setItem(TOKEN_KEY, response.access_token);
}

async function restoreSession() {
  if (!authState.token) {
    authState.initialized = true;
    return;
  }
  try {
    authState.user = await api.me();
  } catch {
    logout();
  } finally {
    authState.initialized = true;
  }
}

async function login(username: string, password: string) {
  const response = await api.login(username, password);
  applyLogin(response);
}

function logout() {
  authState.token = null;
  authState.user = null;
  authState.initialized = true;
  localStorage.removeItem(TOKEN_KEY);
}

export function useAuth() {
  return {
    authState,
    isAuthenticated: computed(() => Boolean(authState.token)),
    login,
    logout,
    restoreSession,
  };
}

export function getStoredToken() {
  return localStorage.getItem(TOKEN_KEY);
}
