import { useCallback, useEffect, useRef, useState } from "react";
import {
  API_BASE,
  MAX_FEED,
  POLL_MS,
  normalizeEvent,
  playAlertTone,
} from "../utils/helpers";

async function fetchJson(url, signal) {
  const res = await fetch(url, { signal });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return res.json();
}

export default function useRealtimeData() {
  const [health, setHealth] = useState({ status: "unknown", model_loaded: false, uptime_seconds: 0 });
  const [modelInfo, setModelInfo] = useState({ features: [], classes: [], feature_count: 0 });
  const [events, setEvents] = useState([]);
  const [humanContext, setHumanContext] = useState({
    people_detected: 0,
    motion_score: 0,
    camera_ok: false,
    last_update: 0,
    image: null,
  });
  const [running, setRunning] = useState(true);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [lastRefresh, setLastRefresh] = useState(new Date());

  const audioCtxRef = useRef(null);
  const seenIdsRef = useRef(new Set());

  const loadHealth = useCallback(async (signal) => {
    const data = await fetchJson(`${API_BASE}/health`, signal);
    setHealth(data);
  }, []);

  const loadModelInfo = useCallback(async (signal) => {
    const data = await fetchJson(`${API_BASE}/model-info`, signal);
    setModelInfo(data);
  }, []);

  const loadHumanContext = useCallback(async (signal) => {
    try {
      const data = await fetchJson(`${API_BASE}/human-context`, signal);
      setHumanContext(data);
    } catch {
      // camera is optional; don't break the dashboard
    }
  }, []);

  const loadEvents = useCallback(async (signal) => {
    const data = await fetchJson(`${API_BASE}/events?limit=${MAX_FEED}`, signal);

    const normalized = (Array.isArray(data) ? data : [])
      .map((e, idx) => normalizeEvent(e, idx))
      .filter(Boolean)
      .sort((a, b) => a.ts - b.ts);

    const fresh = [];
    for (const ev of normalized) {
      if (!seenIdsRef.current.has(ev.id)) {
        seenIdsRef.current.add(ev.id);
        fresh.push(ev);
      }
    }

    if (fresh.length && soundEnabled) {
      const last = fresh[fresh.length - 1];
      const attackNow = last && String(last.label).toUpperCase() !== "BENIGN";

      if (attackNow) {
        try {
          if (!audioCtxRef.current) {
            const Ctx = window.AudioContext || window.webkitAudioContext;
            if (Ctx) audioCtxRef.current = new Ctx();
          }

          if (audioCtxRef.current?.state === "suspended") {
            await audioCtxRef.current.resume();
          }

          const people = Number(humanContext?.people_detected || 0);
          const intensity = people >= 3 ? 2 : people >= 1 ? 1.5 : 1;

          playAlertTone(audioCtxRef.current, intensity);
        } catch {
          // ignore sound failures
        }
      }
    }

    setEvents(normalized.slice(-MAX_FEED).reverse());
  }, [soundEnabled, humanContext]);

  const refresh = useCallback(async () => {
    const controller = new AbortController();
    try {
      await Promise.all([
        loadHealth(controller.signal),
        loadModelInfo(controller.signal),
        loadHumanContext(controller.signal),
        loadEvents(controller.signal),
      ]);
      setLastRefresh(new Date());
    } catch {
      // keep UI resilient
    } finally {
      controller.abort();
    }
  }, [loadEvents, loadHealth, loadModelInfo, loadHumanContext]);

  const toggleSound = useCallback(async () => {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;

      if (soundEnabled) {
        try {
          await audioCtxRef.current?.suspend();
        } catch {}
        setSoundEnabled(false);
        return false;
      }

      if (!Ctx) return false;

      if (!audioCtxRef.current) {
        audioCtxRef.current = new Ctx();
      }

      if (audioCtxRef.current.state === "suspended") {
        await audioCtxRef.current.resume();
      }

      setSoundEnabled(true);
      return true;
    } catch {
      return false;
    }
  }, [soundEnabled]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!running) return;

    const id = setInterval(() => {
      refresh();
    }, POLL_MS);

    return () => clearInterval(id);
  }, [refresh, running]);

  return {
    health,
    modelInfo,
    events,
    humanContext,
    running,
    setRunning,
    refresh,
    soundEnabled,
    toggleSound,
    lastRefresh,
  };
}
