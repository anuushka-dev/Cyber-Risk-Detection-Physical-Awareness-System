export const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";
export const POLL_MS = 400;
export const MAX_FEED = 120;

const WINDOW_MS = 60_000;
const BUCKET_MS = 2_000;

export function isBenign(label) {
  return String(label || "").trim().toUpperCase() === "BENIGN";
}

export function getLabel(raw) {
  return (
    raw?.label ||
    raw?.attack_type ||
    raw?.predicted_label ||
    raw?.result?.label ||
    raw?.prediction?.label ||
    "BENIGN"
  );
}

export function getConfidence(raw) {
  const v =
    raw?.confidence ??
    raw?.score ??
    raw?.result?.confidence ??
    raw?.prediction?.confidence ??
    0;

  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

export function getTimestamp(raw) {
  const v =
    raw?.timestamp ??
    raw?.time ??
    raw?.created_at ??
    raw?.ts ??
    raw?.first_seen;

  if (!v) return Date.now();
  if (typeof v === "number") return v > 1e12 ? v : v * 1000;

  const parsed = Date.parse(v);
  return Number.isNaN(parsed) ? Date.now() : parsed;
}

export function normalizeEvent(raw, idx = 0) {
  const ts = getTimestamp(raw);
  const label = getLabel(raw);
  const confidence = getConfidence(raw);

  return {
    id: raw?.id || raw?.request_id || `${ts}-${idx}-${label}`,
    ts,
    label,
    confidence,
    source_ip:
      raw?.source_ip ||
      raw?.src_ip ||
      raw?.client_ip ||
      raw?.ip ||
      raw?.flow_meta?.src_ip ||
      "—",
    dest_ip:
      raw?.dest_ip ||
      raw?.dst_ip ||
      raw?.server_ip ||
      raw?.flow_meta?.dst_ip ||
      "—",
    protocol: raw?.protocol || raw?.proto || raw?.flow_meta?.protocol || "—",
    raw,
  };
}

export function formatTime(ts) {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString([], { hour12: false });
}

export function labelTone(label) {
  const u = String(label || "").toUpperCase();
  if (u === "BENIGN") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-200";
  if (u.includes("UNCERTAIN")) return "border-amber-500/30 bg-amber-500/10 text-amber-200";
  return "border-red-500/30 bg-red-500/10 text-red-200";
}

function buildBuckets(events) {
  const normalized = (events || [])
    .map((e, idx) => normalizeEvent(e, idx))
    .filter(Boolean);

  const latestTs = normalized.length
    ? Math.max(...normalized.map((e) => e.ts))
    : Date.now();

  const start = latestTs - WINDOW_MS;

  const buckets = Array.from(
    { length: Math.floor(WINDOW_MS / BUCKET_MS) + 1 },
    (_, i) => {
      const ts = start + i * BUCKET_MS;
      return {
        ts,
        time: formatTime(ts),
        count: 0,
        benign: 0,
        attacks: 0,
        sumConfidence: 0,
        total: 0,
        avgConfidence: 0,
        attackRate: 0,
      };
    }
  );

  for (const e of normalized) {
    const idx = Math.floor((e.ts - start) / BUCKET_MS);
    if (idx < 0 || idx >= buckets.length) continue;

    const b = buckets[idx];
    b.total += 1;
    b.sumConfidence += e.confidence || 0;

    if (isBenign(e.label)) b.benign += 1;
    else b.attacks += 1;
  }

  for (const b of buckets) {
    b.count = b.total;
    b.avgConfidence = b.total ? +(b.sumConfidence / b.total).toFixed(3) : 0;
    b.attackRate = b.total ? +(b.attacks / b.total).toFixed(3) : 0;
  }

  return buckets;
}

export function bucketizeEvents(events) {
  return buildBuckets(events);
}

export function buildConfidenceSeries(events) {
  return buildBuckets(events).map((b) => ({
    ts: b.ts,
    time: b.time,
    avgConfidence: b.avgConfidence,
    attackRate: b.attackRate,
  }));
}

export function countByLabel(events) {
  const map = new Map();

  for (const e of events || []) {
    const label = e.label || "UNKNOWN";
    map.set(label, (map.get(label) || 0) + 1);
  }

  const total = Array.isArray(events) && events.length > 0 ? events.length : 0;

  let result = Array.from(map.entries())
    .map(([label, count]) => ({
      label,
      count,
      share: total > 0 ? Number(((count / total) * 100).toFixed(1)) : 0,
    }))
    .sort((a, b) => b.count - a.count);

  if (result.length === 0) {
    return [
      { label: "BENIGN", count: 1, share: 100 },
      { label: "No attacks", count: 0.001, share: 0.1 },
    ];
  }

  if (result.length === 1) {
    result.push({
      label: "No attacks",
      count: 0.001,
      share: 0.1,
    });
  }

  return result;
}

export function playAlertTone(audioCtx, intensity = 1) {
  if (!audioCtx) return;

  const now = audioCtx.currentTime;
  const loud = intensity > 1;

  const makeBeep = (freq, start, duration, gainValue) => {
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();

    osc.type = "square";
    osc.frequency.value = freq;
    gain.gain.value = 0.0001;

    osc.connect(gain);
    gain.connect(audioCtx.destination);

    osc.start(now + start);
    gain.gain.exponentialRampToValueAtTime(gainValue, now + start + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + start + duration);
    osc.stop(now + start + duration + 0.03);
  };

  if (loud) {
    makeBeep(1040, 0.0, 0.14, 0.26);
    makeBeep(920, 0.12, 0.14, 0.24);
    makeBeep(1040, 0.24, 0.14, 0.26);
  } else {
    makeBeep(880, 0.0, 0.16, 0.18);
    makeBeep(660, 0.18, 0.16, 0.16);
  }
}