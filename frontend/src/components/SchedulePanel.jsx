import React from 'react'
import { CalendarDays, Sprout } from 'lucide-react'
import { localizeCropName } from '../utils/geoLocalization'

export default function SchedulePanel({ advisory, t, language = 'en', error, historical = false }) {
  const hindi = language === 'hi'
  const entries = (advisory?.evidence?.schedule || [])
    .filter(entry => !entry.extracted_reference && entry.guidance)
    .slice()
    .sort((a, b) => (a.date || '9999').localeCompare(b.date || '9999'))
  return <section className="space-y-5">
    <div className="flex flex-wrap justify-between items-end gap-3"><div>
      <h2 className="text-xl font-bold text-white flex items-center gap-2"><CalendarDays size={21} className="text-purple-400" />{t?.tabSchedule || (hindi ? 'फसल कैलेंडर' : 'Crop calendar')}</h2>
      <p className="text-sm text-purple-200/80 mt-1">{historical ? (hindi ? 'सहेजा गया कैलेंडर' : 'Saved calendar') : (hindi ? 'SoilMate द्वारा बनाया गया नवीनतम कैलेंडर' : 'The latest calendar created by SoilMate')}</p>
    </div>{advisory?.crop_name && <span className="rounded-full bg-purple-900/50 px-3 py-1.5 text-xs text-purple-200 flex items-center gap-1"><Sprout size={14} />{localizeCropName(advisory.crop_name, language)}</span>}</div>
    {error && <p role="alert" className="text-sm text-red-200">{error}</p>}
    <div className="overflow-x-auto rounded-2xl border border-purple-500/25 bg-dark-950/60">
      <table className="w-full text-left text-sm">
        <thead className="bg-purple-950/40 text-purple-200"><tr><th scope="col" className="px-4 py-3 w-40">{hindi ? 'तारीख' : 'Date'}</th><th scope="col" className="px-4 py-3">{hindi ? 'काम' : 'Task'}</th></tr></thead>
        <tbody className="divide-y divide-purple-500/15">{entries.length ? entries.map((entry, index) => <tr key={`${entry.date || 'undated'}-${index}`} className="align-top"><td className="px-4 py-4 text-purple-200">{entry.date ? `${entry.date}${entry.date_end && entry.date_end !== entry.date ? ` – ${entry.date_end}` : ''}` : entry.days_after_sowing != null ? `${entry.days_after_sowing}${entry.days_after_sowing_end != null ? `–${entry.days_after_sowing_end}` : ''} ${hindi ? 'दिन बुवाई के बाद' : 'days after sowing'}` : (hindi ? 'तारीख उपलब्ध नहीं' : 'Date not available')}</td><td className="px-4 py-4 text-stone-100 whitespace-pre-wrap">{entry.guidance}{entry.source && <a href={entry.source} target="_blank" rel="noreferrer" className="block mt-2 text-xs text-cyan-300 underline">{hindi ? 'स्रोत देखें' : 'View source'}</a>}</td></tr>) : <tr><td colSpan={2} className="px-4 py-6 text-purple-200/80">{hindi ? 'अभी कोई कार्यसूची नहीं है। अपनी फसल और बुवाई की तारीख बताकर कैलेंडर बनाने को कहें।' : 'No schedule yet. Tell SoilMate your crop and sowing date and ask for a calendar.'}</td></tr>}</tbody>
      </table>
    </div>
    {entries.some(entry => !entry.date) && <p className="text-xs text-purple-300">{hindi ? 'जिन कामों की तारीख उपलब्ध नहीं है, उनके लिए बुवाई की तारीख YYYY-MM-DD में बताएं।' : 'For tasks without a date, provide the sowing date in YYYY-MM-DD format.'}</p>}
  </section>
}
