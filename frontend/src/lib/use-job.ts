import { useEffect, useState } from 'react';

import { ApiError, getJob, type Job } from './api';

/** Start one poll every 500 ms, counted from the start of the previous one
 * (docs/API.md). Polls never overlap: one that takes longer is followed at once. */
export const POLL_INTERVAL_MS = 500;
/** GPU start-up can take minutes; stop waiting only after this. */
export const GIVE_UP_AFTER_S = 10 * 60;

export type JobView = {
  job: Job | null;
  /** A final error: the job does not exist (or expired). */
  error: ApiError | null;
  /** The last poll failed on the network; polling continues. */
  offline: boolean;
  /** Not finished after GIVE_UP_AFTER_S: polling stopped. */
  gaveUp: boolean;
};

/** Seconds since the job was created. Uses the server's created_at so a page
 * refresh does not restart the count; assumes the device clock is roughly right. */
export function jobAgeS(job: Job, nowMs = Date.now()): number {
  return Math.max(0, nowMs / 1000 - job.created_at);
}

export function useJob(id: string): JobView {
  const [view, setView] = useState<JobView>({ job: null, error: null, offline: false, gaveUp: false });

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const mountedAt = Date.now();
    let job: Job | null = null;
    setView({ job: null, error: null, offline: false, gaveUp: false });

    async function poll() {
      const startedAt = Date.now();
      let offline = false;
      try {
        job = await getJob(id, controller.signal);
      } catch (e) {
        if (controller.signal.aborted) return;
        if (e instanceof ApiError && e.status === 404) {
          setView((v) => ({ ...v, error: e }));
          return;
        }
        offline = true; // a network blip or a 5xx: keep trying until the deadline
      }
      if (controller.signal.aborted) return;
      const finished = job?.status === 'done' || job?.status === 'failed';
      const age = job ? jobAgeS(job) : (Date.now() - mountedAt) / 1000;
      const gaveUp = !finished && age >= GIVE_UP_AFTER_S;
      setView({ job, error: null, offline, gaveUp });
      if (finished || gaveUp) return;
      const wait = Math.max(0, startedAt + POLL_INTERVAL_MS - Date.now());
      timer = setTimeout(poll, wait);
    }

    poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [id]);

  return view;
}
