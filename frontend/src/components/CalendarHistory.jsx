import React, { useEffect, useState } from 'react'
import { CalendarDays, ArrowLeft } from 'lucide-react'
import { fetchCalendars } from '../services/api'
import SchedulePanel from './SchedulePanel'

export default function CalendarHistory({ language, t, revision }) {
  const [calendars, setCalendars] = useState([])
  const [selected, setSelected] = useState(null)
  const [error, setError] = useState('')
  const hindi = language === 'hi'
  useEffect(() => { let active = true; fetchCalendars().then(items => { if (active) setCalendars(items) }).catch(e => { if (active) setError(e.message) }); return () => { active = false } }, [revision])
  return <div className="rounded-2xl border border-purple-500/25 bg-dark-900/70 p-5 space-y-4">
    {selected ? <><button type="button" onClick={() => setSelected(null)} className="flex items-center gap-2 text-sm text-purple-300 hover:text-white"><ArrowLeft size={16} />{hindi ? 'कैलेंडर इतिहास' : 'Back to calendar history'}</button><SchedulePanel advisory={selected} language={language} t={t} historical /></> : <>
      <h3 className="flex items-center gap-2 font-bold"><CalendarDays size={20} className="text-purple-400" />{hindi ? 'कैलेंडर इतिहास' : 'Calendar history'}</h3>
      {error && <p role="alert" className="text-sm text-red-200">{error}</p>}
      {!error && !calendars.length && <p className="text-sm text-purple-200/70">{hindi ? 'अभी कोई सहेजा हुआ कैलेंडर नहीं है।' : 'No saved calendars yet.'}</p>}
      <div className="space-y-2">{calendars.map(calendar => <button type="button" key={calendar.id} onClick={() => setSelected(calendar)} className="w-full text-left rounded-xl border border-purple-500/20 bg-purple-950/30 hover:bg-purple-900/40 p-3 flex justify-between gap-3"><span className="font-semibold text-sm capitalize">{calendar.crop_name}</span><span className="text-xs text-purple-300">{new Date(calendar.created_at).toLocaleString(language === 'hi' ? 'hi-IN' : undefined)}</span></button>)}</div>
    </>}
  </div>
}
