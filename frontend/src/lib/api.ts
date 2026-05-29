import axios, { AxiosRequestConfig } from "axios";

// In dev: Vite proxy forwards /api/* → http://localhost:8000/*
// In prod: Caddy routes /api/* → api:8000/*
export const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
});

let isRefreshing = false;
let waitQueue: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = [];

function processQueue(error: unknown, token: string | null) {
  waitQueue.forEach((p) => (error ? p.reject(error) : p.resolve(token!)));
  waitQueue = [];
}

api.interceptors.request.use((config) => {
  const stored = localStorage.getItem("auth_tokens");
  if (stored) {
    const { access } = JSON.parse(stored) as { access: string; refresh: string };
    config.headers = config.headers ?? {};
    config.headers["Authorization"] = `Bearer ${access}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config as AxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status !== 401 || original._retry) {
      return Promise.reject(error);
    }
    original._retry = true;

    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        waitQueue.push({
          resolve: (token) => {
            original.headers = original.headers ?? {};
            original.headers["Authorization"] = `Bearer ${token}`;
            resolve(api(original));
          },
          reject,
        });
      });
    }

    isRefreshing = true;
    const stored = localStorage.getItem("auth_tokens");
    if (!stored) {
      isRefreshing = false;
      window.location.href = "/login";
      return Promise.reject(error);
    }

    const { refresh } = JSON.parse(stored) as { access: string; refresh: string };
    try {
      const { data } = await api.post<{ access: string; refresh: string }>(
        "/v1/auth/refresh",
        { refresh }
      );
      localStorage.setItem("auth_tokens", JSON.stringify(data));
      processQueue(null, data.access);
      original.headers = original.headers ?? {};
      original.headers["Authorization"] = `Bearer ${data.access}`;
      return api(original);
    } catch (refreshError) {
      processQueue(refreshError, null);
      localStorage.removeItem("auth_tokens");
      window.location.href = "/login";
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);
