"use client";
import { useState, useEffect, useRef, useMemo } from "react";
import { Network } from "@aptos-labs/ts-sdk";
import { useWallet as useAptosWallet } from "@aptos-labs/wallet-adapter-react";
import { ShelbyClient } from "@shelby-protocol/sdk/browser";
import { useUploadBlobs } from "@shelby-protocol/react";
import { datasetsApi, uploadApi } from "@/lib/api/client";
import { useJobPoller } from "@/lib/useJobPoller";
import { Card, SectionTitle, Button, ProgressBar, Spinner, Badge } from "@/components/ui";
import { WalletGuard } from "@/components/WalletGuard";

type Step = "configure" | "sharding" | "uploading" | "done" | "error";
type Format = "image-tar" | "text-jsonl" | "parquet" | "audio-tar";

type UploadForm = {
  format: Format;
  dataset_dir: string;
  output_dir: string;
  shard_size: number;
  dataset_name: string;
  expiration: string;
};

type ApiError = {
  response?: { data?: { detail?: string } };
  message?: string;
};

type ShardInfo = {
  index: number;
  file: string;
  size_bytes?: number;
};

const FORMATS = [
  { id: "image-tar"  as Format, label: "Image",   icon: "▦", description: "PNG/JPG images with labels.csv",          placeholder_dir: "data/raw_mnist",          placeholder_out: "data/shelbytrain_mnist",   default_shard: 1000  },
  { id: "text-jsonl" as Format, label: "Text",    icon: "≡", description: "JSONL text dataset with text + label",    placeholder_dir: "data/my_dataset.jsonl",   placeholder_out: "data/shelbytrain_text",    default_shard: 10000 },
  { id: "parquet"    as Format, label: "Parquet", icon: "⊞", description: "Tabular data or embeddings in Parquet",   placeholder_dir: "data/my_dataset.parquet", placeholder_out: "data/shelbytrain_parquet", default_shard: 50000 },
  { id: "audio-tar"  as Format, label: "Audio",   icon: "♪", description: "WAV audio files with labels.csv",         placeholder_dir: "data/raw_audio",          placeholder_out: "data/shelbytrain_audio",   default_shard: 500   },
];

function errorMessage(error: unknown) {
  if (typeof error === "object" && error !== null) {
    const e = error as ApiError;
    return e.response?.data?.detail || e.message || "Request failed";
  }
  return "Request failed";
}

function later(fn: () => void) { window.setTimeout(fn, 0); }

function expirationToMicros(expiration: string) {
  const normalized = expiration.trim().toLowerCase();
  const match = normalized.match(/(\d+)\s*(day|days|hour|hours|minute|minutes)/);
  if (!match) return (Date.now() + 7 * 24 * 60 * 60 * 1000) * 1000;

  const amount = Number(match[1]);
  const unit = match[2];
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  const delta =
    unit.startsWith("day") ? amount * day :
    unit.startsWith("hour") ? amount * hour :
    amount * minute;
  return (Date.now() + delta) * 1000;
}

function safeBlobSegment(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "dataset";
}

export default function UploadPage() {
  const [step, setStep]               = useState<Step>("configure");
  const [jobId, setJobId]             = useState<string | null>(null);
  const [uploadJobId, setUploadJobId] = useState<string | null>(null);
  const [datasetId, setDatasetId]     = useState<string>("");
  const [error, setError]             = useState<string | null>(null);
  const [uploading, setUploading]     = useState(false);
  const [dragOver, setDragOver]       = useState(false);
  const [fileInfo, setFileInfo]       = useState<{ name: string; samples: number } | null>(null);
  const [uploadProgress, setUploadProgress] = useState({
    uploaded: 0,
    total: 0,
    current: "",
    lastError: "",
  });
  const fileInputRef                  = useRef<HTMLInputElement>(null);
  const { account, signAndSubmitTransaction } = useAptosWallet();
  const shelbyApiKey = process.env.NEXT_PUBLIC_SHELBY_API_KEY;
  const shelbyClient = useMemo(
    () => new ShelbyClient({
      network: Network.SHELBYNET,
      apiKey: shelbyApiKey,
    }),
    [shelbyApiKey],
  );
  const shelbyUpload = useUploadBlobs({ client: shelbyClient });

  const [form, setForm] = useState<UploadForm>({
    format:       "image-tar",
    dataset_dir:  "data/raw_mnist",
    output_dir:   "data/shelbytrain_mnist",
    shard_size:   1000,
    dataset_name: "mnist-demo",
    expiration:   "in 7 days",
  });

  const shardJob  = useJobPoller(step === "sharding"  ? jobId       : null);
  const uploadJob = useJobPoller(step === "uploading" && uploadJobId ? uploadJobId : null);
  const selectedFormat = FORMATS.find(f => f.id === form.format)!;

  useEffect(() => {
    if (step === "sharding" && shardJob?.status === "done") {
      const id = shardJob.dataset_id || form.output_dir.split("/").pop() || "";
      later(() => {
        setDatasetId(id);
        setStep("uploading");
        startBrowserShelbyUpload(id);
      });
    }
    if (step === "sharding" && shardJob?.status === "error") {
      later(() => { setError(shardJob.error || "Sharding failed"); setStep("error"); });
    }
  }, [shardJob?.status, shardJob?.dataset_id, shardJob?.error]);

  useEffect(() => {
    if (step === "uploading" && uploadJob?.status === "done")  later(() => setStep("done"));
    if (step === "uploading" && uploadJob?.status === "error") later(() => {
      setError(uploadJob.error || "Upload failed"); setStep("error");
    });
  }, [step, uploadJob?.status, uploadJob?.error]);

  const selectFormat = (fmt: Format) => {
    const f = FORMATS.find(x => x.id === fmt)!;
    setForm(prev => ({
      ...prev,
      format:      fmt,
      dataset_dir: f.placeholder_dir,
      output_dir:  f.placeholder_out,
      shard_size:  f.default_shard,
    }));
    setFileInfo(null);
  };

  const handleFile = async (file: File) => {
    const ext = file.name.split(".").pop()?.toLowerCase();
    const supported = ["txt", "jsonl", "csv"];
    if (!supported.includes(ext || "")) {
      setError(`Unsupported file type .${ext}. Supported: .txt .jsonl .csv`);
      return;
    }
    setError(null);
    setUploading(true);
    try {
      const name = file.name.replace(/\.[^.]+$/, "").replace(/\s+/g, "_").toLowerCase();
      const result = await uploadApi.uploadFile(file, name);
      setFileInfo({ name: file.name, samples: result.samples });
      setForm(prev => ({
        ...prev,
        format:       result.format as Format,
        dataset_dir:  result.dataset_dir,
        output_dir:   result.output_dir,
        shard_size:   result.shard_size,
        dataset_name: result.dataset_name,
      }));
    } catch (e: unknown) {
      setError(errorMessage(e));
    } finally {
      setUploading(false);
    }
  };

  const startShard = async () => {
    setError(null);
    try {
      const r = await uploadApi.shard(form);
      setJobId(r.job_id);
      setStep("sharding");
    } catch (e: unknown) {
      setError(errorMessage(e));
      setStep("error");
    }
  };

  const startBrowserShelbyUpload = async (id: string) => {
    if (!account || !signAndSubmitTransaction) {
      setError("Connect an Aptos wallet that can sign Shelby upload transactions.");
      setStep("error");
      return;
    }
    if (!shelbyApiKey) {
      setError("Shelby browser API key is missing. Set NEXT_PUBLIC_SHELBY_API_KEY on Vercel and redeploy the frontend.");
      setStep("error");
      return;
    }

    setUploadJobId(null);
    setUploadProgress({ uploaded: 0, total: 0, current: "Loading shard manifest", lastError: "" });
    try {
      const shardResponse = await datasetsApi.shards(id);
      const shards = (shardResponse.shards ?? []) as ShardInfo[];
      if (!shards.length) throw new Error("No local shards found for this dataset.");

      const uploadPrefix = `${safeBlobSegment(form.dataset_name || id)}-${Date.now().toString(36)}`;
      const blobs = [];
      setUploadProgress({ uploaded: 0, total: shards.length, current: "Preparing shards", lastError: "" });

      for (const shard of shards) {
        setUploadProgress(prev => ({ ...prev, current: shard.file }));
        const bytes = await datasetsApi.shardBytes(id, shard.index);
        blobs.push({
          blobName: `${uploadPrefix}/${shard.file}`,
          blobData: new Uint8Array(bytes),
          index: shard.index,
        });
      }

      setUploadProgress(prev => ({ ...prev, current: "Waiting for wallet signature" }));
      await shelbyUpload.mutateAsync({
        signer: { account, signAndSubmitTransaction },
        blobs: blobs.map(({ blobName, blobData }) => ({ blobName, blobData })),
        expirationMicros: expirationToMicros(form.expiration),
        maxConcurrentUploads: 3,
      });

      setUploadProgress({ uploaded: blobs.length, total: blobs.length, current: "Finalizing manifest", lastError: "" });
      await uploadApi.completeClientUpload({
        dataset_id: id,
        upload_prefix: uploadPrefix,
        shards: blobs.map(({ index, blobName }) => ({ index, blob_name: blobName })),
      });
      setStep("done");
    } catch (e: unknown) {
      const message = errorMessage(e);
      setUploadProgress(prev => ({ ...prev, lastError: message }));
      setError(message);
      setStep("error");
    }
  };

  const resumeUpload = async () => {
    const id = datasetId || form.output_dir.split("/").pop() || "";
    if (!id) return;
    setError(null);
    setDatasetId(id);
    setStep("uploading");
    startBrowserShelbyUpload(id);
  };

  const reset = () => {
    setStep("configure"); setJobId(null); setUploadJobId(null);
    setError(null); setDatasetId(""); setFileInfo(null);
  };

  return (
    <WalletGuard message="Connect your wallet to upload datasets. Your wallet address is used as your Shelby account.">
    <div style={{ width: "100%", maxWidth: 860 }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontFamily: "var(--mono)", fontSize: 20, fontWeight: 500, color: "#2d1b0f" }}>Upload Dataset</h1>
        <p style={{ color: "#7a4a31", fontSize: 13, marginTop: 6 }}>
          Drop a file or configure manually, then push shards to Shelby.
        </p>
      </div>

      {/* Step indicator */}
      <div style={{ display: "flex", gap: 0, marginBottom: 28 }}>
        {(["configure","sharding","uploading","done"] as Step[]).map((s, i) => (
          <div key={s} style={{ display: "flex", alignItems: "center" }}>
            <div style={{
              fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.06em",
              padding: "4px 12px", borderRadius: 4,
              background: step === s ? "var(--green)" : "var(--bg2)",
              color: step === s ? "#000" : "var(--text3)",
              border: "1px solid",
              borderColor: step === s ? "var(--green)" : "var(--border)",
            }}>{s}</div>
            {i < 3 && <div style={{ width: 20, height: 1, background: "var(--border)" }} />}
          </div>
        ))}
      </div>

      {error && (
        <div style={{
          background: "rgba(239,68,68,0.08)", border: "1px solid var(--red)",
          borderRadius: "var(--radius)", padding: "12px 16px", marginBottom: 20,
          fontFamily: "var(--mono)", fontSize: 12, color: "var(--red)",
          lineHeight: 1.6, whiteSpace: "pre-wrap",
        }}>✗ {error}</div>
      )}

      {(step === "configure" || step === "error") && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Drop zone */}
          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => {
              e.preventDefault();
              setDragOver(false);
              const file = e.dataTransfer.files[0];
              if (file) handleFile(file);
            }}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: `2px dashed ${dragOver ? "var(--green)" : "var(--border2)"}`,
              borderRadius: "var(--radius-lg)",
              padding: "32px 24px",
              textAlign: "center",
              cursor: "pointer",
              background: dragOver ? "rgba(0,212,160,0.04)" : "var(--bg1)",
              transition: "all 0.15s",
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.jsonl,.csv"
              style={{ display: "none" }}
              onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
            />
            {uploading ? (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10 }}>
                <Spinner />
                <span style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--text2)" }}>
                  Processing file...
                </span>
              </div>
            ) : fileInfo ? (
              <div>
                <div style={{ color: "var(--green)", fontFamily: "var(--mono)", fontSize: 14, marginBottom: 6 }}>
                  ✓ {fileInfo.name}
                </div>
                <div style={{ color: "var(--text3)", fontFamily: "var(--mono)", fontSize: 12 }}>
                  {fileInfo.samples.toLocaleString()} samples detected — form auto-filled below
                </div>
              </div>
            ) : (
              <div>
                <div style={{ fontSize: 28, marginBottom: 10 }}>↑</div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 14, color: "var(--text)", marginBottom: 6 }}>
                  Drop your file here or click to browse
                </div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text3)" }}>
                  Supported: .txt .jsonl .csv — from anywhere on your computer
                </div>
              </div>
            )}
          </div>

          {/* Divider */}
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
            <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text3)" }}>
              or configure manually
            </span>
            <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
          </div>

          {/* Format selector */}
          <Card>
            <SectionTitle>Dataset format</SectionTitle>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
              {FORMATS.map(fmt => (
                <div key={fmt.id} onClick={() => selectFormat(fmt.id)} style={{
                  padding: "14px 12px",
                  background: form.format === fmt.id ? "rgba(0,212,160,0.08)" : "var(--bg2)",
                  border: `1px solid ${form.format === fmt.id ? "var(--green)" : "var(--border)"}`,
                  borderRadius: "var(--radius)", cursor: "pointer", transition: "all 0.15s",
                }}>
                  <div style={{ fontSize: 20, marginBottom: 8,
                    color: form.format === fmt.id ? "var(--green)" : "var(--text3)" }}>
                    {fmt.icon}
                  </div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 500,
                    color: form.format === fmt.id ? "var(--green)" : "var(--text)", marginBottom: 4 }}>
                    {fmt.label}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text3)", lineHeight: 1.4 }}>
                    {fmt.description}
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {/* Fields */}
          <Card>
            <SectionTitle>Configuration <Badge variant="green">{selectedFormat.label}</Badge></SectionTitle>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {[
                { key: "dataset_dir",  label: form.format === "text-jsonl" || form.format === "parquet" ? "Input file path" : "Dataset directory", placeholder: selectedFormat.placeholder_dir },
                { key: "output_dir",   label: "Output directory",  placeholder: selectedFormat.placeholder_out },
                { key: "dataset_name", label: "Dataset name",      placeholder: "my-dataset" },
                { key: "expiration",   label: "Shelby expiration", placeholder: "in 7 days" },
              ].map(({ key, label, placeholder }) => (
                <label key={key}>
                  <div style={{ fontSize: 11, color: "var(--text3)", fontFamily: "var(--mono)",
                    letterSpacing: "0.08em", marginBottom: 6 }}>{label.toUpperCase()}</div>
                  <input
                    value={(form as any)[key]}
                    onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                    placeholder={placeholder}
                    style={{ width: "100%", background: "var(--bg2)", border: "1px solid var(--border)",
                      borderRadius: "var(--radius)", padding: "8px 12px",
                      color: "var(--text)", fontFamily: "var(--mono)", fontSize: 13, outline: "none" }}
                  />
                </label>
              ))}
              <label>
                <div style={{ fontSize: 11, color: "var(--text3)", fontFamily: "var(--mono)",
                  letterSpacing: "0.08em", marginBottom: 6 }}>SHARD SIZE (samples per shard)</div>
                <input type="number" value={form.shard_size}
                  onChange={e => setForm(f => ({ ...f, shard_size: Number(e.target.value) }))}
                  style={{ width: "100%", background: "var(--bg2)", border: "1px solid var(--border)",
                    borderRadius: "var(--radius)", padding: "8px 12px",
                    color: "var(--text)", fontFamily: "var(--mono)", fontSize: 13, outline: "none" }} />
                <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 4, fontFamily: "var(--mono)" }}>
                  Recommended: {selectedFormat.default_shard.toLocaleString()} for {selectedFormat.label} datasets
                </div>
              </label>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <Button onClick={startShard}>↑ Shard & Upload</Button>
                {step === "error" && (
                  <Button onClick={resumeUpload} variant="ghost">↻ Resume Upload</Button>
                )}
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* SHARDING */}
      {step === "sharding" && (
        <Card>
          <SectionTitle>Sharding {selectedFormat.label} dataset</SectionTitle>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
            <Spinner />
            <span style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--text2)" }}>
              Creating shards from {form.dataset_dir}...
            </span>
          </div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text3)" }}>
            Status: {shardJob?.step ?? "waiting"}
          </div>
        </Card>
      )}

      {/* UPLOADING */}
      {step === "uploading" && (
        <Card>
          <SectionTitle>Uploading to Shelby</SectionTitle>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
            <Spinner />
            <span style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--text2)" }}>
              Uploading shards to Shelby network...
            </span>
          </div>
          {uploadJob && (
            <>
              <ProgressBar
                value={uploadJob.uploaded ?? 0}
                max={uploadJob.total ?? 1}
                label={`${uploadJob.uploaded ?? 0} / ${uploadJob.total ?? "?"} shards`}
              />
              {uploadJob.current_shard && (
                <div style={{ marginTop: 10, fontFamily: "var(--mono)", fontSize: 11, color: "var(--text3)" }}>
                  Current: {uploadJob.current_shard}
                </div>
              )}
              {uploadJob.last_error && (
                <div style={{ marginTop: 6, fontFamily: "var(--mono)", fontSize: 11, color: "var(--amber)" }}>
                  {uploadJob.last_error}
                </div>
              )}
            </>
          )}
          {!uploadJob && (
            <>
              <ProgressBar
                value={uploadProgress.uploaded}
                max={uploadProgress.total || 1}
                label={`${uploadProgress.uploaded} / ${uploadProgress.total || "?"} shards`}
              />
              {uploadProgress.current && (
                <div style={{ marginTop: 10, fontFamily: "var(--mono)", fontSize: 11, color: "var(--text3)" }}>
                  Current: {uploadProgress.current}
                </div>
              )}
              {uploadProgress.lastError && (
                <div style={{ marginTop: 6, fontFamily: "var(--mono)", fontSize: 11, color: "var(--amber)" }}>
                  {uploadProgress.lastError}
                </div>
              )}
            </>
          )}
        </Card>
      )}

      {/* DONE */}
      {step === "done" && (
        <Card>
          <SectionTitle>Upload complete</SectionTitle>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ color: "var(--green)", fontFamily: "var(--mono)", fontSize: 14 }}>
              ✓ All shards uploaded to Shelby
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {[
                { label: "Dataset ID",  value: datasetId },
                { label: "Format",      value: selectedFormat.label },
                { label: "Output dir",  value: form.output_dir },
                { label: "Expires",     value: form.expiration },
              ].map(({ label, value }) => (
                <div key={label} style={{ padding: "10px 12px", background: "var(--bg2)",
                  borderRadius: "var(--radius)", border: "1px solid var(--border)" }}>
                  <div style={{ fontSize: 10, color: "var(--text3)", fontFamily: "var(--mono)",
                    letterSpacing: "0.08em", marginBottom: 4 }}>{label.toUpperCase()}</div>
                  <div style={{ fontSize: 12, color: "var(--text)", fontFamily: "var(--mono)" }}>{value}</div>
                </div>
              ))}
            </div>
            <Button onClick={reset} variant="ghost">↑ Upload another dataset</Button>
          </div>
        </Card>
      )}
    </div>
  );

    </WalletGuard>
  );
}
