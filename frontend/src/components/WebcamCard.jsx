import React, { useEffect, useState } from "react";
import { Camera, Users, Activity } from "lucide-react";
import { API_BASE } from "../utils/helpers";

export default function WebcamCard() {

  const [data, setData] = useState({
    people_detected: 0,
    motion_score: 0,
    camera_ok: false,
    image: null,
    last_update: null
  });

  async function load() {
    try {
      const res = await fetch(`${API_BASE}/human-context`);
      const json = await res.json();
      setData(json);
    } catch (e) {
      console.error("camera fetch error", e);
    }
  }

  useEffect(() => {

    load();

    const id = setInterval(load, 400);

    return () => clearInterval(id);

  }, []);

  const imgSrc =
    data.image
      ? `data:image/jpeg;base64,${data.image}`
      : null;

  return (

    <div className="rounded-3xl border border-slate-800 bg-slate-900/70 backdrop-blur">

      <div className="p-4">

        <div className="flex items-center justify-between mb-3">

          <div>
            <h3 className="text-2xl font-bold">
              Webcam 
            </h3>

            <p className="text-sm text-slate-400">
              Real-time people detection
            </p>

          </div>

          <Camera className="w-30 h-20 text-cyan-300"/>

        </div>


        <div className="rounded-xl overflow-hidden border border-slate-800 bg-black">

          {
            imgSrc
              ? (
                  <img
                    src={imgSrc}
                    alt="camera"
                    className="w-full h-[385px] object-cover"
                  />
                )
              : (
                  <div className="h-[385px] flex items-center justify-center text-slate-500 text-xs">
                    waiting for camera...
                  </div>
                )
          }

        </div>


        <div className="grid grid-cols-2 gap-3 mt-3">

        </div>

      </div>

    </div>

  );

}