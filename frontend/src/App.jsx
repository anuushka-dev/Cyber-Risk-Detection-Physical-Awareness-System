import React, { useMemo } from "react";

import Header from "./components/Header";
import LiveHistogram from "./components/LiveHistogram";
import AlertPanel from "./components/AlertPanel";
import MetricsCards from "./components/MetricsCards";
import LiveFeed from "./components/LiveFeed";
import AttackDistribution from "./components/AttackDistribution";
import SystemInfo from "./components/SystemInfo";
import ConfidenceChart from "./components/ConfidenceChart";
import WebcamCard from "./components/WebcamCard";
import WebcamStats from "./components/WebcamStats";
import useRealtimeData from "./hooks/useRealtimeData";

import {
  bucketizeEvents,
  buildConfidenceSeries,
  countByLabel,
  isBenign,
} from "./utils/helpers";

import "./styles/animations.css";

export default function App() {

  const {

    health,
    modelInfo,
    events,
    humanContext,

    running,
    setRunning,

    refresh,

    soundEnabled,
    toggleSound,

    lastRefresh

  } = useRealtimeData();

  const humanCount =
    humanContext?.people_detected ?? 0;

  const motionScore =
    humanContext?.motion_score ?? 0;



  /* ---------------- data transforms ---------------- */

  const histogramData =
    useMemo(
      () => bucketizeEvents(events),
      [events]
    );


  const confidenceData =
    useMemo(
      () => buildConfidenceSeries(events),
      [events]
    );


  const labelData =
    useMemo(
      () => countByLabel(events),
      [events]
    );


  const total =
    events.length;


  const attackCount =
    events.filter(
      e => !isBenign(e.label)
    ).length;


  const benignCount =
    total - attackCount;


  const avgConfidence =
    total > 0
      ? events.reduce(
          (sum, e) =>
            sum + (Number(e.confidence) || 0),
          0
        ) / total
      : 0;


  const latest =
    events[0] || null;



  return (

    <div className="min-h-screen bg-slate-950 text-slate-100">

      {/* animated background */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">

        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(34,211,238,0.14),transparent_25%),radial-gradient(circle_at_80%_80%,rgba(239,68,68,0.12),transparent_25%),linear-gradient(to_bottom,rgba(2,6,23,1),rgba(15,23,42,1))]" />

        <div className="absolute -top-24 left-1/2 h-72 w-[70rem] -translate-x-1/2 rounded-full bg-cyan-500/10 blur-3xl animate-floatGlow" />

        <div className="absolute bottom-0 right-0 h-64 w-64 rounded-full bg-red-500/10 blur-3xl animate-floatGlow" />

      </div>



      <div className="relative z-10 mx-auto max-w-[1600px] space-y-5 p-4 md:p-6">

        {/* header */}
        <Header
          health={health}
          modelInfo={modelInfo}

          running={running}
          onToggleRunning={() =>
            setRunning(v => !v)
          }

          onRefresh={refresh}

          soundEnabled={soundEnabled}
          onEnableSound={toggleSound}
        />


        <div className="grid gap-5 xl:grid-cols-12">

  {/* histogram */}
  <div className="xl:col-span-8">

    <LiveHistogram data={histogramData} />

  </div>


  {/* alert panel */}
  <div className="xl:col-span-4 xl:row-span-2">

    <AlertPanel
      latest={latest}
      topThreats={labelData}
      attackCount={attackCount}
      soundEnabled={soundEnabled}
    />

  </div>



  {/* webcam */}
  <div className="xl:col-span-5">

    <WebcamCard />

  </div>



  {/* motion + metrics stacked */}
  <div className="xl:col-span-3 flex flex-col gap-5">

    <WebcamStats
      humanCount={humanCount}
      motionScore={motionScore}
    />

    <div className="w-[240%] self-start ]">
    <MetricsCards
      total={total}
      attacks={attackCount}
      benign={benignCount}
      avgConfidence={avgConfidence}
    />
    </div>

  </div>

</div>



        {/* middle section */}
        <div className="grid gap-5 xl:grid-cols-12">

          {/* live feed */}
          <div className="space-y-5 xl:col-span-4">

            <LiveFeed
              events={events}
            />

          </div>



          {/* charts */}
          <div className="space-y-5 xl:col-span-5">

            <ConfidenceChart
              data={confidenceData}
            />

            <AttackDistribution
              data={labelData}
            />

          </div>



          {/* system info */}
          <div className="xl:col-span-3">

            <SystemInfo
              health={health}
              modelInfo={modelInfo}
              events={events}
              lastRefresh={lastRefresh}
            />

          </div>

        </div>



        {/* footer */}
        <div className="pb-4 text-center text-xs text-slate-500">

          Polling every 500ms • Backend:

          {" "}

          {import.meta.env.VITE_API_BASE
            || "http://127.0.0.1:8000"}

          {" "}

          • Sound alert on non-BENIGN events

        </div>

      </div>

    </div>

  );

}