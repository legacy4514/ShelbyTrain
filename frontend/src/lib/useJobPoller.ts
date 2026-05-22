"use client";
import { useEffect, useState } from "react";
import { jobsApi } from "@/lib/api/client";

export interface Job {
  status: "running" | "done" | "error";
  job_id: string;
  step?: string;
  error?: string;
  uploaded?: number;
  total?: number;
  [key: string]: any;
}

export function useJobPoller(jobId: string | null, intervalMs = 1500) {
  const [job, setJob] = useState<Job | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let active = true;

    const poll = async () => {
      while (active) {
        try {
          const data = await jobsApi.get(jobId);
          if (active) setJob(data);
          if (data.status !== "running") break;
        } catch {
          break;
        }
        await new Promise(r => setTimeout(r, intervalMs));
      }
    };

    poll();
    return () => { active = false; };
  }, [jobId, intervalMs]);

  return job;
}
