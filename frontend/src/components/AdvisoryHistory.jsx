import React, { useEffect, useState } from 'react'
import { Calendar, ShieldAlert, BookOpen, RefreshCw, ChevronRight, Sprout, ArrowLeft, Trash2 } from 'lucide-react'
import { fetchAdvisories, fetchAdvisoryDetail, deleteAdvisoryApi } from '../services/api'
import { localizePlaceName, localizeCropName } from '../utils/geoLocalization'

export default function AdvisoryHistory({ sessionId, t, onOpen, onDelete }) {
  const [error, setError] = useState('')
  const [advisories, setAdvisories] = useState([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [deletingId, setDeletingId] = useState(null)

  const loadAdvisories = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await fetchAdvisories({ sessionId })
      setAdvisories(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAdvisories()
  }, [sessionId])

  const openDetail = async (id) => {
    setDetailLoading(true)
    try {
      const detail = await fetchAdvisoryDetail(id)
      onOpen?.(detail)
      setSelected(detail)
    } catch (e) {
      setError(e.message)
    } finally {
      setDetailLoading(false)
    }
  }

  const handleDeleteAdvisory = async (e, id) => {
    e?.stopPropagation()
    const confirmMsg = t?.confirmDelete || 'Are you sure you want to delete this?'
    if (!window.confirm(confirmMsg)) return

    setDeletingId(id)
    try {
      await deleteAdvisoryApi(id)
      onDelete?.(id)
      if (selected?.id === id) {
        setSelected(null)
      }
      await loadAdvisories()
    } catch (err) {
      alert(`Failed to delete advisory: ${err.message}`)
    } finally {
      setDeletingId(null)
    }
  }

  if (selected) {
    return (
      <div className="rounded-2xl border border-purple-500/25 bg-dark-900/70 p-5 shadow-glass space-y-4 backdrop-blur-md">
        <div className="flex items-center justify-between">
          <button
            onClick={() => setSelected(null)}
            className="text-xs font-bold text-purple-300 hover:text-white flex items-center gap-1.5 transition cursor-pointer"
          >
            <ArrowLeft size={14} /> {t?.historyBackToList || 'Back to Advisory List'}
          </button>
          <button
            type="button"
            onClick={(e) => handleDeleteAdvisory(e, selected.id)}
            disabled={deletingId === selected.id}
            className="text-xs text-red-400 hover:text-red-300 hover:bg-red-950/40 px-2.5 py-1 rounded-lg border border-red-500/25 flex items-center gap-1.5 transition cursor-pointer"
          >
            <Trash2 size={13} />
            <span>{t?.deleteAdvisory || 'Delete Advisory'}</span>
          </button>
        </div>

        <div className="flex items-center justify-between pt-2 border-t border-purple-500/20">
          <div>
            <h4 className="text-lg font-bold text-white flex items-center gap-2">
              <Sprout className="text-emerald-400" />
              {localizeCropName(selected.crop_name, t?._langCode || 'hi')} {selected.crop_name_local && `(${selected.crop_name_local})`}
            </h4>
            <p className="text-xs text-purple-300/70">
              {selected.location_name && `${t?.historyLocation || 'Location'}: ${localizePlaceName(selected.location_name, t?._langCode || 'hi')} · `}
              {new Date(selected.created_at).toLocaleDateString()}
            </p>
          </div>
          {selected.season && (
            <span className="text-xs font-bold uppercase px-2.5 py-1 rounded-full bg-purple-900/60 border border-purple-500/30 text-purple-200">
              {selected.season}
            </span>
          )}
        </div>

        <div className="rounded-xl bg-purple-950/40 p-4 border border-purple-500/20 text-xs sm:text-sm text-stone-200 leading-relaxed whitespace-pre-wrap">
          {selected.full_advisory_text}
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-purple-500/25 bg-dark-900/70 p-5 shadow-glass space-y-4 backdrop-blur-md">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <BookOpen className="text-purple-400" size={24} />
          <div>
            <h3 className="text-sm font-bold text-white">{t?.historyAdvisoriesTitle || 'Saved Crop Advisories'}</h3>
            <p className="text-xs text-purple-300/70">{t?.historyAdvisoriesSubtitle || 'Persistent agronomic history saved in database'}</p>
          </div>
        </div>
        <button
          onClick={loadAdvisories}
          className="text-xs text-purple-400 hover:text-white flex items-center gap-1 transition cursor-pointer"
          title="Refresh history"
        >
          <RefreshCw size={12} /> {t?.historyRefresh || 'Refresh'}
        </button>
      </div>

      {error && <p role="alert" className="text-sm text-red-200">{error}</p>}
      {loading && (
        <div className="p-6 text-center text-xs text-purple-300">
          <RefreshCw size={16} className="animate-spin mx-auto mb-2 text-purple-400" />
          {t?.historyAdvisoriesLoading || 'Loading saved advisories...'}
        </div>
      )}

      {!loading && !error && advisories.length === 0 && (
        <div className="p-6 text-center text-xs text-purple-300/70 bg-purple-950/30 rounded-xl border border-purple-500/20">
          <Sprout size={24} className="mx-auto mb-1 text-purple-400 opacity-60" />
          <p className="font-semibold text-white">{t?.historyNoAdvisoriesTitle || 'No saved crop advisories'}</p>
          <p className="mt-1 text-purple-400/80">{t?.historyNoAdvisoriesDesc || 'Advisories generated during chat are automatically saved here.'}</p>
        </div>
      )}

      {advisories.length > 0 && (
        <div className="divide-y divide-purple-500/15 border border-purple-500/20 rounded-xl overflow-hidden max-h-72 overflow-y-auto scroll-thin">
          {advisories.map((a) => (
            <div
              key={a.id}
              role="button" tabIndex={0} onKeyDown={e => { if (e.key === 'Enter') openDetail(a.id) }}
              onClick={() => openDetail(a.id)}
              className="w-full text-left p-3 flex items-center justify-between bg-dark-900/40 hover:bg-purple-950/40 transition cursor-pointer group"
            >
              <div className="min-w-0 flex-1 pr-2">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-xs text-white">
                    {localizeCropName(a.crop_name, t?._langCode || 'hi')} {a.crop_name_local && `(${a.crop_name_local})`}
                  </span>
                  {a.season && (
                    <span className="text-[10px] uppercase font-bold text-purple-300 bg-purple-950/80 px-1.5 py-0.2 rounded border border-purple-500/30">
                      {a.season}
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-purple-300/70 mt-1 flex items-center gap-2">
                  {a.location_name && <span>📍 {localizePlaceName(a.location_name, t?._langCode || 'hi')}</span>}
                  <span>{new Date(a.created_at).toLocaleDateString([], { month: 'short', day: 'numeric' })}</span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={(e) => handleDeleteAdvisory(e, a.id)}
                  disabled={deletingId === a.id}
                  className="p-1.5 rounded-lg text-purple-400 hover:text-red-400 hover:bg-red-950/40 transition opacity-80 group-hover:opacity-100 cursor-pointer"
                  title={t?.deleteAdvisory || 'Delete Advisory'}
                >
                  <Trash2 size={14} className={deletingId === a.id ? 'animate-pulse text-red-400' : ''} />
                </button>
                <ChevronRight size={16} className="text-purple-400" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
