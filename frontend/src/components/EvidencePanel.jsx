import React from 'react'
export default function EvidencePanel({ evidence }) {
  if (!evidence?.tools?.length) return null
  return <section className="p-4 border border-purple-500/25 rounded-xl space-y-3 text-xs">
    <h3 className="font-bold text-purple-200">Sources and limitations</h3><p>{evidence.note}</p>
    {evidence.tools.filter(t => t.tool !== 'record_crop_schedule').map((t, i) => {
      const data = t.outputs || {}
      return <div key={i} className="border-t border-purple-500/20 pt-2 space-y-1">
        <p className="font-semibold">{t.tool.replaceAll('_', ' ')} ? {data.error ? 'Unavailable' : data.data_kind?.replaceAll('_', ' ') || 'Reference'}</p>
        <p>{data.error || data.note || data.coverage}</p>
        {data.source?.startsWith('https://') && <a className="text-cyan-300 underline break-all" href={data.source} target="_blank" rel="noreferrer">{data.source}</a>}
        {data.retrieved_at && <p>Retrieved {new Date(data.retrieved_at).toLocaleString()}</p>}
      </div>
    })}
  </section>
}
