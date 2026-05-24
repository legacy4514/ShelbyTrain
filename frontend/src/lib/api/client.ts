import axios from "axios";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "",
  timeout: 120000,
});

// Attach wallet address to every request
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const addr = (window as any).__shelby_wallet_address;
    if (addr) config.headers["X-Wallet-Address"] = addr;
  }
  return config;
});

export default api;

export const datasetsApi = {
  manifest: (id: string) => api.get(`/api/datasets/${id}/manifest`).then(r => r.data),
  reconstruct: (id: string) =>
    api.post(`/api/datasets/${id}/reconstruct`, {}, { responseType: "blob" }).then(r => {
      const disposition = String(r.headers["content-disposition"] ?? "");
      const match = disposition.match(/filename="([^"]+)"/);
      return {
        blob: r.data as Blob,
        filename: match?.[1] ?? `${id}.download`,
      };
    }),
  list:    ()              => api.get("/api/datasets").then(r => r.data),
  get:     (id: string)   => api.get(`/api/datasets/${id}`).then(r => r.data),
  shards:  (id: string)   => api.get(`/api/datasets/${id}/shards`).then(r => r.data),
  shardBytes: (id: string, index: number) =>
    api.get(`/api/datasets/${id}/shards/${index}/download`, { responseType: "arraybuffer" })
      .then(r => r.data as ArrayBuffer),
  preview: (id: string, rows = 10) => api.get(`/api/datasets/${id}/preview`, { params: { rows } }).then(r => r.data),
};

export const uploadApi = {
  uploadFile: (file: File | File[], datasetName: string) => {
    const form = new FormData();
    const files = Array.isArray(file) ? file : [file];
    files.forEach((item) => form.append("files", item));
    form.append("dataset_name", datasetName);
    return api.post("/api/upload/files", form, {
      headers: { "Content-Type": "multipart/form-data" },
    }).then(r => r.data);
  },
  shard:   (body: { dataset_dir: string; output_dir: string; shard_size: number; dataset_name: string; format: string }) =>
    api.post("/api/upload/shard", body).then(r => r.data),
  toShelby: (dataset_id: string, expiration = "in 7 days") =>
    api.post("/api/upload/shelby", { dataset_id, expiration }).then(r => r.data),
  completeClientUpload: (body: { dataset_id: string; upload_prefix: string; shards: { index: number; blob_name: string }[] }) =>
    api.post("/api/upload/shelby/client-complete", body).then(r => r.data),
  resumeShelby: (dataset_id: string, expiration = "in 7 days") =>
    api.post("/api/upload/shelby/resume", { dataset_id, expiration }).then(r => r.data),
};

export const jobsApi = {
  get: (job_id: string) => api.get(`/api/jobs/${job_id}`).then(r => r.data),
};

export const benchmarkApi = {
  run: (body: { dataset_id: string; modes: string[]; batch_size: number; batches: number; max_shards: number }) =>
    api.post("/api/benchmark/run", body).then(r => r.data),
  get:        (run_id: string) => api.get(`/api/benchmark/${run_id}`).then(r => r.data),
  allResults: ()               => api.get("/api/benchmark/results/all").then(r => r.data),
  history:    ()               => api.get("/api/benchmark/history").then(r => r.data),
};

export const cacheApi = {
  stats:  ()             => api.get("/api/cache/stats").then(r => r.data),
  evict:  (key: string)  => api.delete(`/api/cache/evict/${key}`).then(r => r.data),
  clear:  ()             => api.delete("/api/cache/clear").then(r => r.data),
};

export const dashboardApi = {
  pipeline: () => api.get("/api/dashboard/pipeline").then(r => r.data),
};
