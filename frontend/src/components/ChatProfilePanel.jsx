import React, { useState, useEffect } from 'react'
import { User, MapPin, Sprout, Layers, Globe, Database, Sparkles, CheckCircle2, AlertCircle } from 'lucide-react'
import { localizePlaceName, localizeState, localizeCropName, localizeSoilType } from '../utils/geoLocalization'

export default function ChatProfilePanel({ location, language, sessionId, farmerProfile, t, onSave }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { setDraft(farmerProfile || {}) }, [farmerProfile])
  const save = async e => {
    e.preventDefault(); setSaving(true); setError('')
    try {
      const values = {}
      for (const key of ['location_name', 'state', 'district', 'primary_crop', 'soil_type', 'language', 'land_size_acres', 'latitude', 'longitude']) {
        if (draft[key] !== farmerProfile?.[key]) values[key] = ['land_size_acres', 'latitude', 'longitude'].includes(key) ? (draft[key] === '' ? null : Number(draft[key])) : draft[key] || null
      }
      await onSave(values); setEditing(false)
    } catch (err) { setError(err.message) } finally { setSaving(false) }
  }
  const locName = farmerProfile?.location_name || location?.name
  const lat = farmerProfile?.latitude ?? location?.lat
  const lon = farmerProfile?.longitude ?? location?.lon
  const state = farmerProfile?.state || location?.state
  const district = farmerProfile?.district
  const land = farmerProfile?.land_size_acres
  const crops = farmerProfile?.primary_crop
  const soil = farmerProfile?.soil_type

  return (
    <div className="space-y-4">
      <button onClick={() => setEditing(!editing)} className="px-4 py-2 rounded-xl border border-purple-400 text-sm">{editing ? 'Cancel editing' : 'Edit farm profile'}</button>
      {error && <p role="alert" className="text-red-200 text-sm">{error}</p>}
      {editing && <form onSubmit={save} className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-4 border border-purple-500/30 rounded-xl">
        {['location_name', 'state', 'district', 'primary_crop', 'soil_type', 'land_size_acres', 'latitude', 'longitude'].map(key => <label key={key} className="text-xs space-y-1 capitalize">{key.replaceAll('_', ' ')}
          <input type={['land_size_acres', 'latitude', 'longitude'].includes(key) ? 'number' : 'text'} step="any" maxLength={200} value={draft[key] ?? ''} onChange={e => setDraft({ ...draft, [key]: e.target.value })} className="block w-full p-2 bg-purple-950 rounded-lg border border-purple-500/30" />
        </label>)}
        <label className="text-xs">Conversation language<select value={draft.language || language} onChange={e => setDraft({ ...draft, language: e.target.value })} className="block w-full p-2 bg-purple-950 rounded-lg">{['en','hi','te','ta','kn','bn','mr','gu','pa','ml','od','ur'].map(code => <option key={code}>{code}</option>)}</select></label>
        <button disabled={saving} className="p-2 bg-purple-700 rounded-lg">{saving ? 'Saving...' : 'Save profile'}</button>
      </form>}
      {/* Profile Overview Card */}
      <div className="rounded-2xl border border-purple-500/25 bg-dark-900/70 p-5 shadow-[0_8px_32px_0_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-4">
        <div className="flex items-center justify-between border-b border-purple-500/20 pb-3">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-tr from-purple-700 to-indigo-600 text-white shadow-glass">
              <User size={22} />
            </div>
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                {t?.profileTitle || 'Farmer Profile & Memory'}
                <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded-full border border-emerald-500/30">
                  {sessionId ? 'SAVED SESSION' : 'NOT SAVED YET'}
                </span>
              </h2>
              <p className="text-xs text-purple-300/70">
                {t?.profileSubtitle || 'Learned autonomously by SoilMate from your voice & chat'}
              </p>
            </div>
          </div>
          {sessionId && (
            <span className="text-[10px] font-mono text-purple-400 bg-purple-950/80 px-2.5 py-1 rounded-lg border border-purple-500/20">
              ID: {sessionId.slice(0, 10)}...
            </span>
          )}
        </div>

        {/* Profile Attributes Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          {/* Location */}
          <div className="rounded-xl bg-purple-950/40 p-3 border border-purple-500/15 space-y-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-purple-400 flex items-center gap-1">
              <MapPin size={13} className="text-cyan-400" /> {t?.profileFarmLocation || 'Farm Location'}
            </span>
            {locName ? (
              <div>
                <p className="font-bold text-white text-sm">{localizePlaceName(locName, t?._langCode || 'hi')}</p>
                {lat != null && lon != null && (
                  <p className="text-[11px] font-mono text-cyan-300">
                    {lat.toFixed(2)}° N, {lon.toFixed(2)}° E {state && `· ${localizeState(state, t?._langCode || 'hi')}`}
                  </p>
                )}
              </div>
            ) : (
              <p className="text-purple-300/60 italic">{t?.profileLocationEmpty || 'Not set yet. Say your village in chat.'}</p>
            )}
          </div>

          {/* Land Size */}
          <div className="rounded-xl bg-purple-950/40 p-3 border border-purple-500/15 space-y-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-purple-400 flex items-center gap-1">
              <Layers size={13} className="text-emerald-400" /> {t?.profileLandholding || 'Landholding Area'}
            </span>
            {land ? (
              <p className="font-bold text-white text-sm">{land} {t?.profileAcres || 'Acres'}</p>
            ) : (
              <p className="text-purple-300/60 italic">{t?.profileLandholdingEmpty || 'Not specified (e.g. "I have 5 acres")'}</p>
            )}
          </div>

          {/* Primary Crops */}
          <div className="rounded-xl bg-purple-950/40 p-3 border border-purple-500/15 space-y-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-purple-400 flex items-center gap-1">
              <Sprout size={13} className="text-amber-400" /> {t?.profileCrops || 'Cultivated Crops'}
            </span>
            {crops ? (
              <p className="font-bold text-white text-sm">{localizeCropName(crops, t?._langCode || 'hi')}</p>
            ) : (
              <p className="text-purple-300/60 italic">{t?.profileCropsEmpty || 'Not specified (e.g. "I grow wheat and mustard")'}</p>
            )}
          </div>

          {/* Soil Type */}
          <div className="rounded-xl bg-purple-950/40 p-3 border border-purple-500/15 space-y-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-purple-400 flex items-center gap-1">
              <Database size={13} className="text-purple-400" /> {t?.profileSoil || 'Soil Type'}
            </span>
            {soil ? (
              <p className="font-bold text-white text-sm">{localizeSoilType(soil, t?._langCode || 'hi')}</p>
            ) : (
              <p className="text-purple-300/60 italic">{t?.profileSoilEmpty || 'Not specified (e.g. "Black cotton soil")'}</p>
            )}
          </div>
        </div>

        {/* Profile Memory Note */}
        <div className="rounded-xl bg-purple-950/30 border border-purple-500/20 p-3 text-xs text-purple-200 flex items-start gap-2.5">
          <Sparkles size={16} className="text-cyan-400 shrink-0 mt-0.5" />
          <div className="leading-relaxed">
            <strong className="text-white">{t?.profileMemoryActive || 'Conversational Memory Active'}:</strong> {t?.profileMemoryDesc || 'Whenever you mention your village, acres, or crops in voice or text, SoilMate geocodes your farm, saves this profile in SQLite, and remembers it across all future questions so you never have to repeat yourself.'}
          </div>
        </div>
      </div>
    </div>
  )
}

