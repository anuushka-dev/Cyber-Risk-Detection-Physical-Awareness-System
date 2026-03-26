export default function WebcamStats({
  humanCount = 0,
  motionScore = 0
}) {

  return (

    <div className="rounded-xl border h-[180px] border-slate-800 bg-slate-900 p-4">

      <div className="text-sm text-slate-400">
        Humans detected
      </div>

      <div className="text-2xl text-green-400 font-semibold mb-4">
        {humanCount}
      </div>


      <div className="text-sm text-slate-400">
        Motion score
      </div>

      <div className="text-xl text-yellow-400 font-semibold">
        {motionScore}
      </div>

    </div>

  );

}