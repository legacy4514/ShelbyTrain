"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { datasetsApi, benchmarkApi } from "@/lib/api/client";
import { useJobPoller } from "@/lib/useJobPoller";
import { Card, SectionTitle, Button, StatCard, Badge, Spinner } from "@/components/ui";
import { WalletGuard } from "@/components/WalletGuard";

type BenchmarkMode = "local" | "shelby_cold" | "shelby_cached";

type BenchmarkResult = {
  batches: number;
  batch_size: number;
  samples: number;
  time_to_first_batch_sec: number;
  total_time_sec: number;
  samples_per_sec: number;
  cache_hits?: number;
  cache_misses?: number;
  download_sec?: number;
  extract_sec?: number;
};

type DatasetSummary = {
  id: string;
  name: string;
};

type BenchmarkForm = {
  dataset_id: string;
  modes: BenchmarkMode[];
  batch_size: number;
  batches: number;
  max_shards: number;
};

type ApiError = {
  response?: { data?: { detail?: string } };
  message?: string;
};

const MODE_COLORS: Record<BenchmarkMode, string> = {
  local: "#7F77DD",
  shelby_cold: "#f59e0b",
  shelby_cached: "#00d4a0",
};

const MODE_LABELS: Record<BenchmarkMode, string> = {
  local: "Local disk",
  shelby_cold: "Shelby cold",
  shelby_cached: "Shelby cached",
};

const NUMBER_FIELDS = [
  { key: "batches", label: "Batches" },
  { key: "max_shards", label: "Max shards" },
] as const;

const BENCHMARK_MODES = Object.keys(MODE_LABELS) as BenchmarkMode[];

function isApiError(error: unknown): error is ApiError {
  return typeof error === "object" && error !== null;
}

function isBenchmarkMode(mode: unknown): mode is BenchmarkMode {
  return typeof mode === "string" && BENCHMARK_MODES.includes(mode as BenchmarkMode);
}

function modeLabel(mode: unknown) {
  return isBenchmarkMode(mode) ? MODE_LABELS[mode] : String(mode);
}

export default function BenchmarkPage() {
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<BenchmarkForm>({
    dataset_id: "",
    modes: ["local", "shelby_cold", "shelby_cached"],
    batch_size: 32,
    batches: 50,
    max_shards: 5,
  });

  const { data: datasets } = useQuery({ queryKey: ["datasets"], queryFn: datasetsApi.list });

  const job = useJobPoller(runId, 2000);
  const running = job?.status === "running";
  const jobErrors = job?.errors as Record<string, string> | undefined;
  const hasJobErrors = Boolean(job?.status === "error" || (jobErrors && Object.keys(jobErrors).length > 0));

  const startBenchmark = async () => {
    if (!form.dataset_id) { setError("Select a dataset first"); return; }
    if (form.modes.length === 0) { setError("Select at least one benchmark mode"); return; }
    setError(null);
    try {
      const r = await benchmarkApi.run(form);
      setRunId(r.run_id);
    } catch (e: unknown) {
      setError(isApiError(e) ? e.response?.data?.detail || e.message || "Benchmark failed" : "Benchmark failed");
    }
  };

  const activeResults = job ? job.results : null;
  const displayResults = activeResults && Object.keys(activeResults).length > 0 ? activeResults : null;
  const resultEntries = displayResults
    ? Object.entries(displayResults) as [BenchmarkMode, BenchmarkResult][]
    : [];

  const throughputData = resultEntries
    .map(([mode, r]) => ({
        mode: MODE_LABELS[mode] ?? mode,
        value: r.samples_per_sec,
        color: MODE_COLORS[mode] ?? "#888",
      }));

  const initData = resultEntries
    .map(([mode, r]) => ({
        mode: MODE_LABELS[mode] ?? mode,
        value: r.time_to_first_batch_sec,
        color: MODE_COLORS[mode] ?? "#888",
      }));

  const cachedResult = displayResults?.shelby_cached;
  const coldResult   = displayResults?.shelby_cold;
  const localResult  = displayResults?.local;
  const speedup = cachedResult && coldResult
    ? (coldResult.time_to_first_batch_sec / cachedResult.time_to_first_batch_sec).toFixed(1)
    : null;

  return (
    <WalletGuard message="Connect your wallet to run benchmarks. Your wallet address is used as your Shelby account.">
    <div style={{ width: "100%", maxWidth: 1280 }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontFamily: "var(--mono)", fontSize: 20, fontWeight: 500, color: "#2d1b0f" }}>Benchmark</h1>
        <p style={{ color: "#7a4a31", fontSize: 13, marginTop: 6 }}>
          Compare local, Shelby cold, and Shelby cached training throughput.
        </p>
      </div>

      <Card>
        <SectionTitle>Run configuration</SectionTitle>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14, marginBottom: 20 }}>
          <label>
            <div style={{ fontSize: 11, color: "var(--text3)", fontFamily: "var(--mono)",
              letterSpacing: "0.08em", marginBottom: 6 }}>DATASET</div>
            <select value={form.dataset_id}
              onChange={e => setForm(f => ({ ...f, dataset_id: e.target.value }))}
              style={{ width: "100%", background: "var(--bg2)", border: "1px solid var(--border)",
                borderRadius: "var(--radius)", padding: "7px 10px",
                color: "var(--text)", fontFamily: "var(--mono)", fontSize: 12, outline: "none" }}>
              <option value="">Select dataset...</option>
              {datasets?.datasets?.map((d: DatasetSummary) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </label>
          {NUMBER_FIELDS.map(({ key, label }) => (
            <label key={key}>
              <div style={{ fontSize: 11, color: "var(--text3)", fontFamily: "var(--mono)",
                letterSpacing: "0.08em", marginBottom: 6 }}>{label.toUpperCase()}</div>
              <input type="number" value={form[key]}
                onChange={e => setForm(f => ({ ...f, [key]: Number(e.target.value) }))}
                style={{ width: "100%", background: "var(--bg2)", border: "1px solid var(--border)",
                  borderRadius: "var(--radius)", padding: "7px 10px",
                  color: "var(--text)", fontFamily: "var(--mono)", fontSize: 12, outline: "none" }} />
            </label>
          ))}
        </div>

        <div style={{ display: "flex", gap: 16, marginBottom: 20 }}>
          {BENCHMARK_MODES.map((mode) => (
            <label key={mode} style={{ display: "flex", alignItems: "center", gap: 6,
              cursor: "pointer", fontFamily: "var(--mono)", fontSize: 12, color: "var(--text2)" }}>
              <input type="checkbox" checked={form.modes.includes(mode)}
                onChange={e => setForm(f => ({
                  ...f,
                  modes: e.target.checked ? [...f.modes, mode] : f.modes.filter(m => m !== mode),
                }))} />
              <span style={{ color: MODE_COLORS[mode] }}>■</span> {MODE_LABELS[mode]}
            </label>
          ))}
        </div>

        {error && (
          <div style={{
            color: "var(--red)",
            fontFamily: "var(--mono)",
            fontSize: 12,
            marginBottom: 12,
            overflowWrap: "anywhere",
            whiteSpace: "pre-wrap",
          }}>
            ✗ {error}
          </div>
        )}

        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <Button onClick={startBenchmark} disabled={running}>
            {running ? "Running..." : "◈ Run Benchmark"}
          </Button>
          {running && (
            <div style={{ display: "flex", alignItems: "center", gap: 8,
              fontFamily: "var(--mono)", fontSize: 12, color: "var(--text2)" }}>
              <Spinner size={14} />
              <span>{job?.current_mode ? `Running ${modeLabel(job.current_mode)}...` : "Initializing..."}</span>
            </div>
          )}
          {job?.status === "done" && <Badge variant="green">Complete</Badge>}
          {job?.status === "error" && <Badge variant="red">Failed</Badge>}
        </div>

        {hasJobErrors && (
          <div style={{
            marginTop: 14,
            border: "1px solid rgba(239,68,68,0.35)",
            background: "rgba(239,68,68,0.08)",
            borderRadius: "var(--radius)",
            padding: "10px 12px",
            color: "var(--red)",
            fontFamily: "var(--mono)",
            fontSize: 11,
            lineHeight: 1.6,
            overflowWrap: "anywhere",
            whiteSpace: "pre-wrap",
          }}>
            <div>{job?.error ?? "Some benchmark modes failed"}</div>
            {jobErrors && Object.entries(jobErrors).map(([mode, message]) => (
              <div key={mode}>
                {modeLabel(mode)}: {message}
              </div>
            ))}
          </div>
        )}
      </Card>

      {displayResults && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, margin: "20px 0" }}>
            <StatCard label="Cache speedup"     value={speedup ? `${speedup}x` : "—"} accent="green" />
            <StatCard label="Cached init"        value={cachedResult?.time_to_first_batch_sec ?? "—"} unit="s" accent="green" />
            <StatCard label="Cold init"          value={coldResult?.time_to_first_batch_sec ?? "—"} unit="s" accent="amber" />
            <StatCard label="Local throughput"   value={localResult?.samples_per_sec?.toLocaleString() ?? "—"} unit="s/s" accent="blue" />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <Card>
              <SectionTitle>Throughput (samples / sec)</SectionTitle>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={throughputData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
                  <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="mode" tick={{ fontSize: 10, fill: "var(--text3)" }} />
                  <YAxis tick={{ fontSize: 10, fill: "var(--text3)" }} />
                  <Tooltip contentStyle={{ background: "var(--bg2)", border: "1px solid var(--border)", fontSize: 11 }}
                    formatter={(v: unknown) => [`${Number(v).toLocaleString()} samp/s`, "Throughput"]} />
                  <Bar dataKey="value" radius={[3,3,0,0]}>
                    {throughputData.map((d, i) => <Cell key={i} fill={d.color} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Card>

            <Card>
              <SectionTitle>Init latency (seconds to first batch)</SectionTitle>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={initData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
                  <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="mode" tick={{ fontSize: 10, fill: "var(--text3)" }} />
                  <YAxis tick={{ fontSize: 10, fill: "var(--text3)" }} />
                  <Tooltip contentStyle={{ background: "var(--bg2)", border: "1px solid var(--border)", fontSize: 11 }}
                    formatter={(v: unknown) => [`${Number(v)}s`, "Init latency"]} />
                  <Bar dataKey="value" radius={[3,3,0,0]}>
                    {initData.map((d, i) => <Cell key={i} fill={d.color} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>

          <Card style={{ marginTop: 16 }}>
            <SectionTitle>Raw results</SectionTitle>
            <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--mono)", fontSize: 11 }}>
              <thead>
                <tr>
                  {["Mode","Batches","Samples","Time (s)","Init (s)","Cache H/M","Download","Extract","Samp/s"].map(h => (
                    <th key={h} style={{ textAlign: "left", padding: "6px 12px",
                      color: "var(--text3)", borderBottom: "1px solid var(--border)",
                      fontWeight: 500, letterSpacing: "0.06em" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {resultEntries.map(([mode, r]) => (
                  <tr key={mode}>
                    <td style={{ padding: "8px 12px", color: MODE_COLORS[mode] ?? "var(--text)" }}>{MODE_LABELS[mode] ?? mode}</td>
                    <td style={{ padding: "8px 12px", color: "var(--text2)" }}>{r.batches}</td>
                    <td style={{ padding: "8px 12px", color: "var(--text2)" }}>{r.samples?.toLocaleString()}</td>
                    <td style={{ padding: "8px 12px", color: "var(--text2)" }}>{r.total_time_sec}</td>
                    <td style={{ padding: "8px 12px", color: "var(--text2)" }}>{r.time_to_first_batch_sec}</td>
                    <td style={{ padding: "8px 12px", color: "var(--text2)" }}>
                      {r.cache_hits ?? 0}/{r.cache_misses ?? 0}
                    </td>
                    <td style={{ padding: "8px 12px", color: "var(--text2)" }}>
                      {r.download_sec?.toFixed?.(3) ?? "—"}s
                    </td>
                    <td style={{ padding: "8px 12px", color: "var(--text2)" }}>
                      {r.extract_sec?.toFixed?.(3) ?? "—"}s
                    </td>
                    <td style={{ padding: "8px 12px", color: mode === "shelby_cached" ? "var(--green)" : "var(--text)" }}>
                      {r.samples_per_sec?.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
    </WalletGuard>
  );
}
