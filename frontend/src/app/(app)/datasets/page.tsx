"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { datasetsApi, uploadApi } from "@/lib/api/client";
import { useJobPoller } from "@/lib/useJobPoller";
import { Card, SectionTitle, Badge, StatCard, Button, ProgressBar, Spinner } from "@/components/ui";
import { WalletGuard } from "@/components/WalletGuard";

type DatasetSummary = {
  id: string;
  name: string;
  uploaded?: boolean;
  total_samples?: number;
  shard_count?: number;
  format?: string;
  lifecycle_status?: string;
  ready_shards?: number;
  failed_shards?: number;
  state_counts?: Record<string, number>;
};

type DatasetShard = {
  index: number;
  file: string;
  samples: number;
  size_bytes?: number;
  blob_name?: string;
  lifecycle_status?: string;
  last_error?: string | null;
};

type PreviewRow = Record<string, string | number | boolean | null>;

function lifecycleVariant(status?: string): "default" | "green" | "amber" | "red" | "blue" {
  if (status === "ready" || status === "verified" || status === "cached") return "green";
  if (status === "syncing" || status === "uploading" || status === "uploaded") return "amber";
  if (status === "attention" || status === "failed" || status === "expired") return "red";
  if (status === "local" || status === "local_created") return "blue";
  return "default";
}

function lifecycleLabel(status?: string) {
  return (status ?? "local").replace("_", " ");
}

function updateAfterEffect(callback: () => void) {
  window.setTimeout(callback, 0);
}

export default function DatasetsPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showManifest, setShowManifest] = useState(false);
  const [resumeJobId, setResumeJobId] = useState<string | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [reconstructing, setReconstructing] = useState(false);
  const [reconstructError, setReconstructError] = useState<string | null>(null);

  const { data: list, isLoading, refetch: refetchList } = useQuery({
    queryKey: ["datasets"],
    queryFn: datasetsApi.list,
    refetchInterval: 5000,
  });

  const { data: detail, refetch: refetchDetail } = useQuery({
    queryKey: ["dataset", selected],
    queryFn: () => datasetsApi.get(selected!),
    enabled: !!selected,
  });

  const resumeJob = useJobPoller(resumeJobId);

  const { data: manifestData } = useQuery({
    queryKey: ["manifest", selected],
    queryFn: () => datasetsApi.manifest(selected!),
    enabled: !!selected,
  });

  const { data: preview } = useQuery({
    queryKey: ["preview", selected],
    queryFn: () => datasetsApi.preview(selected!, 8),
    enabled: !!selected,
  });

  const datasets = list?.datasets ?? [];
  const canResume = Boolean(
    selected &&
    detail &&
    detail.lifecycle_status !== "ready" &&
    (detail.shard_count ?? 0) > 0
  );

  useEffect(() => {
    if (!resumeJob || resumeJob.status === "running") return;
    refetchList();
    refetchDetail();
    if (resumeJob.status === "error") {
      updateAfterEffect(() => setResumeError(resumeJob.error || "Resume upload failed"));
    }
  }, [refetchDetail, refetchList, resumeJob]);

  const resumeUpload = async () => {
    if (!selected) return;
    setResumeError(null);
    try {
      const r = await uploadApi.resumeShelby(selected);
      setResumeJobId(r.job_id);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Resume upload failed";
      setResumeError(message);
    }
  };

  const reconstructDataset = async () => {
    if (!selected) return;
    setReconstructError(null);
    setReconstructing(true);
    try {
      const result = await datasetsApi.reconstruct(selected);
      const url = URL.createObjectURL(result.blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = result.filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Reconstruct failed";
      setReconstructError(message);
    } finally {
      setReconstructing(false);
    }
  };

  return (
    <WalletGuard message="Connect your wallet to view datasets. Your wallet address is used as your Shelby account.">
    <div style={{ width: "100%", maxWidth: 1280 }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontFamily: "var(--mono)", fontSize: 20, fontWeight: 500, color: "#2d1b0f" }}>Datasets</h1>
        <p style={{ color: "#7a4a31", fontSize: 13, marginTop: 6 }}>
          All sharded datasets found under <span style={{ color: "var(--text)", fontFamily: "var(--mono)" }}>data/</span>
        </p>
      </div>

      {isLoading && (
        <div style={{ color: "var(--text3)", fontFamily: "var(--mono)", fontSize: 13 }}>Scanning datasets...</div>
      )}

      {!isLoading && datasets.length === 0 && (
        <Card>
          <div style={{ color: "var(--text3)", fontSize: 13, fontFamily: "var(--mono)" }}>
            No datasets found. Run the upload flow to create one.
          </div>
        </Card>
      )}

      <div style={{ display: "grid", gridTemplateColumns: selected ? "320px 1fr" : "1fr", gap: 18 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {(datasets as DatasetSummary[]).map((d) => (
            <div key={d.id} onClick={() => setSelected(d.id === selected ? null : d.id)}
              style={{
                padding: "14px 16px",
                background: selected === d.id ? "var(--bg2)" : "var(--bg1)",
                border: `1px solid ${selected === d.id ? "var(--green-dim)" : "var(--border)"}`,
                borderRadius: "var(--radius-lg)",
                cursor: "pointer",
              }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--text)" }}>{d.name}</span>
                <Badge variant={lifecycleVariant(d.lifecycle_status)}>
                  {lifecycleLabel(d.lifecycle_status)}
                </Badge>
              </div>
              <div style={{ display: "flex", gap: 16 }}>
                {[
                  { label: "samples", value: d.total_samples?.toLocaleString() },
                  { label: "shards",  value: d.shard_count },
                  { label: "ready", value: `${d.ready_shards ?? 0}/${d.shard_count ?? 0}` },
                  { label: "format",  value: d.format ?? "—" },
                ].map(({ label, value }) => (
                  <div key={label}>
                    <div style={{ fontSize: 10, color: "var(--text3)", fontFamily: "var(--mono)", letterSpacing: "0.06em" }}>{label}</div>
                    <div style={{ fontSize: 12, color: "var(--text2)", fontFamily: "var(--mono)" }}>{value}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {selected && detail && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
              <StatCard label="Total samples" value={detail.total_samples?.toLocaleString() ?? "—"} />
              <StatCard label="Ready shards"  value={`${detail.ready_shards ?? 0}/${detail.shard_count ?? 0}`} accent="green" />
              <StatCard label="Failed shards" value={detail.failed_shards ?? 0} accent={detail.failed_shards ? "red" : "blue"} />
            </div>

            <Card>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
                <div>
                  <SectionTitle>Upload Recovery</SectionTitle>
                  <div style={{ color: "var(--text2)", fontFamily: "var(--mono)", fontSize: 12 }}>
                    {detail.lifecycle_status === "ready"
                      ? "All shards are verified for Shelby-backed benchmarks."
                      : "Resume retries only shards that are not verified or cached."}
                  </div>
                </div>
                <Button onClick={resumeUpload} disabled={!canResume || resumeJob?.status === "running"}>
                  {resumeJob?.status === "running" ? "Resuming..." : "↻ Resume Upload"}
                </Button>
              </div>

              {resumeJob?.status === "running" && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10,
                    color: "var(--text2)", fontFamily: "var(--mono)", fontSize: 12 }}>
                    <Spinner size={14} />
                    <span>Retrying unverified shards...</span>
                  </div>
                  <ProgressBar
                    value={resumeJob.uploaded ?? detail.ready_shards ?? 0}
                    max={resumeJob.total ?? detail.shard_count ?? 1}
                    label={`${resumeJob.uploaded ?? detail.ready_shards ?? 0} / ${resumeJob.total ?? detail.shard_count ?? "?"} verified`}
                  />
                </div>
              )}

              {resumeError && (
                <div style={{ marginTop: 14, color: "var(--red)", fontFamily: "var(--mono)",
                  fontSize: 12, lineHeight: 1.6, overflowWrap: "anywhere", whiteSpace: "pre-wrap" }}>
                  ✗ {resumeError}
                </div>
              )}
            </Card>

            <Card>
              <SectionTitle>Share dataset</SectionTitle>
              <div style={{ fontSize: 13, color: "var(--text2)", marginBottom: 14, lineHeight: 1.6 }}>
                Share this manifest with your team. Anyone with this file can load the dataset
                using ShelbyTrain — no account needed, just a Shelby API key.
              </div>

              {/* Usage code */}
              <div style={{ background: "var(--bg3)", borderRadius: "var(--radius)",
                padding: "14px 16px", marginBottom: 14,
                fontFamily: "var(--mono)", fontSize: 11, color: "var(--text2)",
                lineHeight: 1.8, overflowX: "auto" }}>
                <div style={{ color: "var(--text3)", marginBottom: 6 }}># Install</div>
                <div>pip install shelbytrain</div>
                <div style={{ marginTop: 8, color: "var(--text3)" }}># Use</div>
                <div>from shelbytrain import load_dataset, ShelbyHTTPClient</div>
                <div>client = ShelbyHTTPClient(account=<span style={{color:"var(--green)"}}>"0x..."</span>, api_key=<span style={{color:"var(--green)"}}>"AG-..."</span>)</div>
                <div>dataset = load_dataset(<span style={{color:"var(--green)"}}>"manifest.uploaded.json"</span>, client=client)</div>
              </div>

              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button
                  onClick={() => {
                    if (manifestData?.manifest) {
                      navigator.clipboard.writeText(
                        JSON.stringify(manifestData.manifest, null, 2)
                      );
                      setCopied(true);
                      setTimeout(() => setCopied(false), 2000);
                    }
                  }}
                  style={{
                    fontFamily: "var(--mono)", fontSize: 12,
                    padding: "7px 16px",
                    background: copied ? "var(--green)" : "var(--bg2)",
                    border: "1px solid",
                    borderColor: copied ? "var(--green)" : "var(--border2)",
                    borderRadius: "var(--radius)",
                    color: copied ? "#000" : "var(--text2)",
                    cursor: "pointer", transition: "all 0.15s",
                  }}
                >
                  {copied ? "✓ Copied!" : "⎘ Copy manifest.json"}
                </button>

                <button
                  onClick={() => setShowManifest(s => !s)}
                  style={{
                    fontFamily: "var(--mono)", fontSize: 12,
                    padding: "7px 16px",
                    background: "transparent",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius)",
                    color: "var(--text3)",
                    cursor: "pointer",
                  }}
                >
                  {showManifest ? "▲ Hide manifest" : "▼ View manifest"}
                </button>

                <button
                  onClick={() => {
                    if (manifestData?.manifest) {
                      const blob = new Blob(
                        [JSON.stringify(manifestData.manifest, null, 2)],
                        { type: "application/json" }
                      );
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = "manifest.uploaded.json";
                      a.click();
                      URL.revokeObjectURL(url);
                    }
                  }}
                  style={{
                    fontFamily: "var(--mono)", fontSize: 12,
                    padding: "7px 16px",
                    background: "var(--green)",
                    border: "none",
                    borderRadius: "var(--radius)",
                    color: "#000",
                    cursor: "pointer", fontWeight: 600,
                  }}
                >
                  ↓ Download manifest
                </button>

                <button
                  onClick={reconstructDataset}
                  disabled={!detail.uploaded || reconstructing}
                  style={{
                    fontFamily: "var(--mono)", fontSize: 12,
                    padding: "7px 16px",
                    background: detail.uploaded ? "var(--bg2)" : "var(--bg1)",
                    border: "1px solid var(--border2)",
                    borderRadius: "var(--radius)",
                    color: detail.uploaded ? "var(--text2)" : "var(--text3)",
                    cursor: detail.uploaded && !reconstructing ? "pointer" : "not-allowed",
                  }}
                >
                  {reconstructing ? "Reconstructing..." : "↓ Reconstruct data"}
                </button>
              </div>

              {reconstructError && (
                <div style={{ marginTop: 14, color: "var(--red)", fontFamily: "var(--mono)",
                  fontSize: 12, lineHeight: 1.6, overflowWrap: "anywhere", whiteSpace: "pre-wrap" }}>
                  ✗ {reconstructError}
                </div>
              )}

              {showManifest && manifestData?.manifest && (
                <div style={{
                  marginTop: 14,
                  background: "var(--bg3)",
                  borderRadius: "var(--radius)",
                  padding: "14px 16px",
                  fontFamily: "var(--mono)", fontSize: 10,
                  color: "var(--text2)",
                  maxHeight: 300,
                  overflowY: "auto",
                  whiteSpace: "pre",
                  lineHeight: 1.6,
                }}>
                  {JSON.stringify(manifestData.manifest, null, 2)}
                </div>
              )}
            </Card>

            <Card>
              <SectionTitle>Shards</SectionTitle>
              <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--mono)", fontSize: 11 }}>
                <thead>
                  <tr>
                    {["#", "File", "State", "Samples", "Size", "Blob name", "Error"].map(h => (
                      <th key={h} style={{ textAlign: "left", padding: "6px 10px",
                        color: "var(--text3)", borderBottom: "1px solid var(--border)",
                        fontWeight: 500, letterSpacing: "0.06em" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(detail.shards as DatasetShard[] | undefined)?.map((s) => (
                    <tr key={s.index} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "7px 10px", color: "var(--text3)" }}>{s.index}</td>
                      <td style={{ padding: "7px 10px", color: "var(--text)" }}>{s.file}</td>
                      <td style={{ padding: "7px 10px" }}>
                        <Badge variant={lifecycleVariant(s.lifecycle_status)}>
                          {lifecycleLabel(s.lifecycle_status)}
                        </Badge>
                      </td>
                      <td style={{ padding: "7px 10px", color: "var(--text2)" }}>{s.samples}</td>
                      <td style={{ padding: "7px 10px", color: "var(--text2)" }}>
                        {s.size_bytes ? `${(s.size_bytes / 1024).toFixed(0)} KB` : "—"}
                      </td>
                      <td style={{ padding: "7px 10px", color: "var(--text3)", maxWidth: 180,
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {s.blob_name}
                      </td>
                      <td style={{ padding: "7px 10px", color: "var(--red)", maxWidth: 220,
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {s.last_error ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>

            <Card>
              <SectionTitle>Sample preview — shard 0</SectionTitle>
              {preview?.samples?.length > 0 ? (
                <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--mono)", fontSize: 11 }}>
                  <thead>
                    <tr>
                      {Object.keys(preview.samples[0]).map(k => (
                        <th key={k} style={{ textAlign: "left", padding: "6px 10px",
                          color: "var(--text3)", borderBottom: "1px solid var(--border)",
                          fontWeight: 500, letterSpacing: "0.06em" }}>{k}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(preview.samples as PreviewRow[]).map((row, i) => (
                      <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                        {Object.values(row).map((v, j) => (
                          <td key={j} style={{ padding: "7px 10px", color: "var(--text2)" }}>{String(v)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div style={{ color: "var(--text3)", fontSize: 12, fontFamily: "var(--mono)" }}>No preview available</div>
              )}
            </Card>
          </div>
        )}
      </div>
    </div>
    </WalletGuard>
  );
}
