"use client";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { dashboardApi } from "@/lib/api/client";
import { Card, StatCard, SectionTitle, Badge } from "@/components/ui";
import Link from "next/link";
import { WalletGuard } from "@/components/WalletGuard";

type BenchmarkMode = "local" | "shelby_cold" | "shelby_cached";

type DatasetSummary = {
  id: string;
  name: string;
  total_samples?: number;
  shard_count?: number;
  ready_shards?: number;
  failed_shards?: number;
  lifecycle_status?: string;
};

type BenchmarkResult = {
  samples_per_sec?: number;
  time_to_first_batch_sec?: number;
  cache_hits?: number;
  cache_misses?: number;
  download_sec?: number;
};

type BenchmarkRun = {
  run_id: string;
  dataset_name?: string;
  status: "done" | "error";
  completed_at?: string;
  results?: Partial<Record<BenchmarkMode, BenchmarkResult>>;
  errors?: Record<string, string>;
  speedups?: {
    cache_init_speedup?: number;
    cached_vs_local_throughput?: number;
  };
};

type PipelineSummary = {
  dataset_count: number;
  total_shards: number;
  ready_shards: number;
  failed_shards: number;
  readiness_pct: number;
  datasets: DatasetSummary[];
  cache?: { shard_count?: number; total_mb?: number };
  benchmark_runs: number;
  successful_benchmark_runs: number;
  failed_benchmark_runs: number;
  latest_benchmark?: BenchmarkRun | null;
  recent_benchmarks?: BenchmarkRun[];
};

const MODE_LABELS: Record<BenchmarkMode, string> = {
  local: "Local disk",
  shelby_cold: "Shelby cold",
  shelby_cached: "Shelby cached",
};

const MODE_COLORS: Record<BenchmarkMode, string> = {
  local: "#7F77DD",
  shelby_cold: "#f59e0b",
  shelby_cached: "#ff4fb8",
};

function lifecycleVariant(status?: string): "default" | "green" | "amber" | "red" | "blue" {
  if (status === "ready") return "green";
  if (status === "syncing") return "amber";
  if (status === "attention") return "red";
  if (status === "local") return "blue";
  return "default";
}

function formatDate(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export default function DashboardPage() {
  const { data } = useQuery<PipelineSummary>({
    queryKey: ["pipeline"],
    queryFn: dashboardApi.pipeline,
    refetchInterval: 5000,
  });

  const latest = data?.latest_benchmark;
  const latestResults = latest?.results ?? {};
  const performanceData = (Object.entries(MODE_LABELS) as [BenchmarkMode, string][])
    .map(([mode, label]) => ({
      mode: label,
      throughput: latestResults[mode]?.samples_per_sec ?? 0,
      color: MODE_COLORS[mode],
    }))
    .filter(row => row.throughput > 0);

  return (
    <WalletGuard message="Connect your wallet to view your dashboard. Your wallet address is used as your Shelby account.">
    <div style={{ width: "100%", maxWidth: 1440 }}>
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontFamily: "var(--mono)", fontSize: 22, fontWeight: 600,
          color: "#2d1b0f" }}>
          AI Pipeline Dashboard
        </h1>
        <p style={{ color: "#7a4a31", fontSize: 13, marginTop: 6 }}>
          Dataset lifecycle, Shelby readiness, cache state, and benchmark history.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 16, marginBottom: 22 }}>
        <StatCard label="Readiness" value={`${data?.readiness_pct ?? 0}%`} accent="green" />
        <StatCard label="Ready shards" value={`${data?.ready_shards ?? 0}/${data?.total_shards ?? 0}`} accent="green" />
        <StatCard label="Cached shards" value={data?.cache?.shard_count ?? "—"} accent="amber" />
        <StatCard label="Benchmarks" value={data?.benchmark_runs ?? "—"} accent="blue" />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.1fr 0.9fr", gap: 18, marginBottom: 18 }}>
        <Card>
          <SectionTitle>Pipeline stages</SectionTitle>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
            {[
              { label: "Datasets", value: data?.dataset_count ?? 0, state: (data?.dataset_count ?? 0) > 0 ? "ready" : "local" },
              { label: "Verified", value: data?.ready_shards ?? 0, state: (data?.ready_shards ?? 0) > 0 ? "ready" : "local" },
              { label: "Cache", value: data?.cache?.shard_count ?? 0, state: (data?.cache?.shard_count ?? 0) > 0 ? "ready" : "local" },
              { label: "Failures", value: data?.failed_shards ?? 0, state: (data?.failed_shards ?? 0) > 0 ? "attention" : "ready" },
            ].map(stage => (
              <div key={stage.label} style={{
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                background: "var(--bg2)",
                padding: "14px",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text3)", letterSpacing: "0.08em" }}>
                    {stage.label.toUpperCase()}
                  </span>
                  <Badge variant={lifecycleVariant(stage.state)}>{stage.state}</Badge>
                </div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 24, color: "var(--text)" }}>{stage.value}</div>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <SectionTitle>Latest benchmark</SectionTitle>
          {!latest ? (
            <p style={{ color: "var(--text3)", fontSize: 13 }}>
              No benchmark history yet. <Link href="/benchmark" style={{ color: "var(--green)" }}>Run benchmark</Link>
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--text)" }}>
                    {latest.dataset_name ?? "dataset"}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 2 }}>
                    {formatDate(latest.completed_at)}
                  </div>
                </div>
                <Badge variant={latest.status === "done" ? "green" : "red"}>{latest.status}</Badge>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: 12 }}>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text3)", letterSpacing: "0.08em" }}>
                    CACHE INIT SPEEDUP
                  </div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 22, color: "var(--green)", marginTop: 6 }}>
                    {latest.speedups?.cache_init_speedup ? `${latest.speedups.cache_init_speedup.toFixed(1)}x` : "—"}
                  </div>
                </div>
                <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: 12 }}>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text3)", letterSpacing: "0.08em" }}>
                    CACHED VS LOCAL
                  </div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 22, color: "var(--blue)", marginTop: 6 }}>
                    {latest.speedups?.cached_vs_local_throughput ? `${latest.speedups.cached_vs_local_throughput.toFixed(2)}x` : "—"}
                  </div>
                </div>
              </div>
            </div>
          )}
        </Card>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18, marginBottom: 18 }}>
        <Card>
          <SectionTitle>Latest throughput</SectionTitle>
          {performanceData.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={performanceData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="mode" tick={{ fontSize: 10, fill: "var(--text3)" }} />
                <YAxis tick={{ fontSize: 10, fill: "var(--text3)" }} />
                <Tooltip contentStyle={{ background: "var(--bg2)", border: "1px solid var(--border)", fontSize: 11 }}
                  formatter={(v: unknown) => [`${Number(v).toLocaleString()} samp/s`, "Throughput"]} />
                <Bar dataKey="throughput" radius={[3,3,0,0]}>
                  {performanceData.map((d) => <Cell key={d.mode} fill={d.color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ color: "var(--text3)", fontFamily: "var(--mono)", fontSize: 12 }}>No successful mode results yet.</div>
          )}
        </Card>

        <Card>
          <SectionTitle>Dataset readiness</SectionTitle>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {data?.datasets?.length ? data.datasets.slice(0, 5).map((dataset) => (
              <Link key={dataset.id} href="/datasets" style={{
                display: "grid",
                gridTemplateColumns: "1fr auto",
                gap: 12,
                padding: "10px 12px",
                background: "var(--bg2)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
              }}>
                <div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--text)" }}>{dataset.name}</div>
                  <div style={{ color: "var(--text3)", fontSize: 11, marginTop: 3 }}>
                    {dataset.total_samples?.toLocaleString()} samples · {dataset.ready_shards ?? 0}/{dataset.shard_count ?? 0} ready
                  </div>
                </div>
                <Badge variant={lifecycleVariant(dataset.lifecycle_status)}>
                  {dataset.lifecycle_status ?? "local"}
                </Badge>
              </Link>
            )) : (
              <div style={{ color: "var(--text3)", fontFamily: "var(--mono)", fontSize: 12 }}>
                No datasets found. <Link href="/upload" style={{ color: "var(--green)" }}>Upload dataset</Link>
              </div>
            )}
          </div>
        </Card>
      </div>

      <Card>
        <SectionTitle>Benchmark history</SectionTitle>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--mono)", fontSize: 11 }}>
          <thead>
            <tr>
              {["Run", "Dataset", "Status", "Completed", "Local", "Cold", "Cached", "Speedup"].map(h => (
                <th key={h} style={{ textAlign: "left", padding: "7px 10px",
                  color: "var(--text3)", borderBottom: "1px solid var(--border)",
                  fontWeight: 500, letterSpacing: "0.06em" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(data?.recent_benchmarks ?? []).map((run) => (
              <tr key={run.run_id} style={{ borderBottom: "1px solid var(--border)" }}>
                <td style={{ padding: "8px 10px", color: "var(--text3)" }}>{run.run_id.slice(0, 8)}</td>
                <td style={{ padding: "8px 10px", color: "var(--text)" }}>{run.dataset_name ?? "—"}</td>
                <td style={{ padding: "8px 10px" }}>
                  <Badge variant={run.status === "done" ? "green" : "red"}>{run.status}</Badge>
                </td>
                <td style={{ padding: "8px 10px", color: "var(--text2)" }}>{formatDate(run.completed_at)}</td>
                {(["local", "shelby_cold", "shelby_cached"] as BenchmarkMode[]).map(mode => (
                  <td key={mode} style={{ padding: "8px 10px", color: "var(--text2)" }}>
                    {run.results?.[mode]?.samples_per_sec?.toLocaleString() ?? "—"}
                  </td>
                ))}
                <td style={{ padding: "8px 10px", color: "var(--green)" }}>
                  {run.speedups?.cache_init_speedup ? `${run.speedups.cache_init_speedup.toFixed(1)}x` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
    </WalletGuard>
  );
}
