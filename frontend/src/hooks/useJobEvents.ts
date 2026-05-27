import { useEffect, useRef } from 'react';

export interface LiveJob {
  id: string;
  job_type: string;
  status: string;
  progress: number;
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  error_text?: string | null;
  created_at: string;
  updated_at: string;
}

interface JobEventPayload {
  event?: {
    id: number;
    job_id: string;
    event_type: string;
    message: string;
    progress?: number | null;
    payload: Record<string, unknown>;
    created_at: string;
  };
}

interface JobSnapshotPayload {
  job?: LiveJob;
}

async function readJob(jobId: string): Promise<LiveJob> {
  const response = await fetch(`/api/jobs/${jobId}`);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Request failed: ${response.status}`);
  }
  return payload as LiveJob;
}

export function useJobEvents(
  jobId: string | null | undefined,
  options: {
    enabled?: boolean;
    onJob: (job: LiveJob) => void;
    onError?: (error: Error) => void;
    pollIntervalMs?: number;
  },
) {
  const { enabled = true, onJob, onError, pollIntervalMs = 1800 } = options;
  const lastEventIdRef = useRef(0);

  useEffect(() => {
    if (!jobId || !enabled) {
      return;
    }
    let stopped = false;
    let fallbackTimer: number | undefined;
    let source: EventSource | null = null;
    lastEventIdRef.current = 0;

    const poll = async () => {
      try {
        const job = await readJob(jobId);
        if (!stopped) {
          onJob(job);
        }
      } catch (error) {
        if (!stopped) {
          onError?.(error instanceof Error ? error : new Error(String(error)));
        }
      }
    };

    const startFallback = () => {
      if (fallbackTimer !== undefined) {
        return;
      }
      void poll();
      fallbackTimer = window.setInterval(() => void poll(), pollIntervalMs);
    };

    if (typeof EventSource === 'undefined') {
      startFallback();
      return () => {
        stopped = true;
        if (fallbackTimer !== undefined) window.clearInterval(fallbackTimer);
      };
    }

    const streamUrl = `/api/jobs/${jobId}/events/stream?after_id=${lastEventIdRef.current}`;
    source = new EventSource(streamUrl);
    source.addEventListener('snapshot', (message) => {
      try {
        const payload = JSON.parse(message.data) as JobSnapshotPayload;
        if (payload.job) {
          onJob(payload.job);
        }
      } catch (error) {
        onError?.(error instanceof Error ? error : new Error(String(error)));
      }
    });
    source.addEventListener('job_event', (message) => {
      try {
        const payload = JSON.parse(message.data) as JobEventPayload;
        if (payload.event?.id) {
          lastEventIdRef.current = Math.max(lastEventIdRef.current, payload.event.id);
        }
        void poll();
      } catch (error) {
        onError?.(error instanceof Error ? error : new Error(String(error)));
      }
    });
    source.onerror = () => {
      source?.close();
      source = null;
      startFallback();
    };

    return () => {
      stopped = true;
      source?.close();
      if (fallbackTimer !== undefined) window.clearInterval(fallbackTimer);
    };
  }, [enabled, jobId, onError, onJob, pollIntervalMs]);
}
