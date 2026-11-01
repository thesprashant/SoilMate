import React from 'react'
import { Activity, CheckCircle2, AlertCircle } from 'lucide-react'

const labels = {
  get_weather: 'Weather', get_soil_data: 'SoilGrids', get_mandi_prices: 'Mandi prices',
  query_crop_database: 'Crop reference', record_crop_schedule: 'Crop schedule',
  get_pest_and_disease_risk: 'Pest information', get_government_schemes: 'Government schemes',
  update_farmer_profile: 'Farmer profile'
}

export default function AgentTraceView({ toolCalls }) {
  if (!toolCalls?.length) return null
  return <div className="w-full min-w-0 rounded-xl border border-purple-500/25 bg-purple-950/30 p-3 text-xs space-y-2">
    <h3 className="flex items-center gap-2 font-bold text-purple-200"><Activity size={14} className="text-cyan-400" />Agent activity <span className="text-purple-400 font-normal">({toolCalls.length})</span></h3>
    {toolCalls.map((call, index) => {
      const failed = call.status === 'error' || call.status === 'unavailable' || call.outputs?.status === 'unavailable' || !!call.outputs?.error
      return <div key={`${call.tool}-${index}`} className="min-w-0 rounded-lg border border-purple-500/20 bg-dark-950/60 p-2.5 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-semibold text-purple-200">{labels[call.tool] || call.tool}</span><span className={`inline-flex items-center gap-1 ${failed ? 'text-amber-300' : 'text-emerald-300'}`}>{failed ? <AlertCircle size={13} /> : <CheckCircle2 size={13} />}{failed ? 'Unsuccessful' : 'Successful'}</span></div>
      </div>
    })}
  </div>
}
