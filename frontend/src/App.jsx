import React, { useState, useEffect, useRef } from 'react'
import ChatPanel from './components/ChatPanel'
import DashboardPanel from './components/DashboardPanel'
import { createSession, fetchChatHistory, fetchSessionDetail, fetchAdvisoryDetail, fetchAdvisories, fetchCalendars, updateProfile } from './services/api'
import { stopCurrentAudio } from './utils/audioManager'
const remembered = key => { try { return localStorage.getItem(key) || 'hi' } catch { return 'hi' } }
export default function App() {
  const [uiLanguage, setUiLanguage] = useState(() => remembered('soilmate_ui_lang'))
  const [spokenLanguage, setSpokenLanguage] = useState(() => remembered('soilmate_spoken_lang'))
  const [location, setLocation] = useState(null)
  const [farmerProfile, setFarmerProfile] = useState(null)
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [streamingEvent, setStreamingEvent] = useState(null)
  const [liveTraces, setLiveTraces] = useState([])
  const [activeTab, setActiveTab] = useState('advice')
  const [chatWidth, setChatWidth] = useState(38)
  const layoutRef = useRef(null)
  const [latestAdvisory, setLatestAdvisory] = useState(null)
  const [latestCalendar, setLatestCalendar] = useState(null)
  const [calendarError, setCalendarError] = useState('')
  const [calendarRevision, setCalendarRevision] = useState(0)
  const [generation, setGeneration] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const version = useRef(0)
  const pendingSession = useRef(null)
  const latestAssistantMessage = [...messages].reverse().find(m => m.role === 'assistant')
  const latestToolCalls = liveTraces.length ? liveTraces : latestAssistantMessage?.tool_calls || []
  useEffect(() => { try { localStorage.setItem('soilmate_ui_lang', uiLanguage); localStorage.setItem('soilmate_spoken_lang', spokenLanguage) } catch {} }, [uiLanguage, spokenLanguage])
  const applyProfile = profile => {
    setFarmerProfile(profile)
    setLocation(profile?.latitude != null && profile?.longitude != null ? { name: profile.location_name, lat: profile.latitude, lon: profile.longitude, state: profile.state } : null)
  }
  const reset = () => {
    stopCurrentAudio(); version.current += 1; pendingSession.current = null
    setGeneration(version.current); setSessionId(null); setMessages([]); setStreamingEvent(null); setLiveTraces([])
    setLatestAdvisory(null); applyProfile(null); setError(''); setLoading(false); setActiveTab('advice')
  }
  const ensureSession = async () => {
    if (sessionId) return sessionId
    const current = version.current
    if (!pendingSession.current) pendingSession.current = createSession()
    try {
      const sess = await pendingSession.current
      if (version.current !== current) throw new DOMException('Session changed', 'AbortError')
      setSessionId(sess.id); return sess.id
    } finally { if (version.current === current) pendingSession.current = null }
  }
  const selectSession = async sid => {
    reset(); const current = version.current; setLoading(true)
    try {
      const [history, profile, advisories] = await Promise.all([fetchChatHistory(sid), fetchSessionDetail(sid), fetchAdvisories({ sessionId: sid, limit: 1 })])
      if (current !== version.current) return
      setSessionId(sid); setMessages(history); applyProfile(profile)
      if (profile.language) setSpokenLanguage(profile.language)
      if (advisories[0]) {
        const detail = await fetchAdvisoryDetail(advisories[0].id)
        if (current === version.current) setLatestAdvisory(detail)
      }
    } catch (e) { if (current === version.current) setError(e.message) }
    finally { if (current === version.current) setLoading(false) }
  }
  const saveProfile = async values => {
    const current = version.current
    const sid = await ensureSession()
    const profile = await updateProfile(sid, values)
    if (current === version.current) { applyProfile(profile); if (profile.language) setSpokenLanguage(profile.language) }
  }
  useEffect(() => {
    const id = latestAssistantMessage?.advisory_id
    if (!id) return
    let cancelled = false
    fetchAdvisoryDetail(id).then(advice => { if (!cancelled) setLatestAdvisory(advice) }).catch(e => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [latestAssistantMessage?.advisory_id, generation])
  useEffect(() => {
    let cancelled = false
    fetchCalendars(1).then(items => { if (!cancelled) { setLatestCalendar(items[0] || null); setCalendarError('') } })
      .catch(e => { if (!cancelled) setCalendarError(e.message) })
    return () => { cancelled = true }
  }, [latestAssistantMessage?.advisory_id, generation, calendarRevision])
  const resize = clientX => {
    const rect = layoutRef.current?.getBoundingClientRect()
    if (rect) setChatWidth(Math.min(70, Math.max(25, ((clientX - rect.left) / rect.width) * 100)))
  }
  const startResize = event => {
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    resize(event.clientX)
  }
  return <div ref={layoutRef} className="flex flex-col lg:flex-row min-h-screen lg:h-screen w-full lg:overflow-hidden bg-dark-950 font-sans text-stone-100">
    <div className="w-full lg:w-[var(--chat-width)] lg:h-full lg:shrink-0" style={{ '--chat-width': `${chatWidth}%` }}>
    <ChatPanel key={generation} uiLanguage={uiLanguage} setUiLanguage={v => { setUiLanguage(v); setSpokenLanguage(v) }} spokenLanguage={spokenLanguage} setSpokenLanguage={setSpokenLanguage}
      location={location} setLocation={setLocation} sessionId={sessionId} setSessionId={setSessionId} ensureSession={ensureSession}
      messages={messages} setMessages={setMessages} onUserActivity={() => setLiveTraces([])} onNewSession={reset}
      streamingEvent={streamingEvent} setStreamingEvent={setStreamingEvent} setFarmerProfile={applyProfile} liveTraces={liveTraces} setLiveTraces={setLiveTraces} disabled={loading} />
    </div>
    <div role="separator" aria-label="Resize chat panel" aria-orientation="vertical" aria-valuemin={25} aria-valuemax={70} aria-valuenow={Math.round(chatWidth)} tabIndex={0}
      onPointerDown={startResize} onPointerMove={event => { if (event.currentTarget.hasPointerCapture(event.pointerId)) resize(event.clientX) }}
      onKeyDown={event => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); setChatWidth(width => Math.min(70, Math.max(25, width + (event.key === 'ArrowRight' ? 2 : -2)))) } }}
      className="hidden lg:flex w-2 shrink-0 cursor-col-resize touch-none items-center justify-center bg-purple-950/40 hover:bg-purple-700/60 focus:bg-purple-700/60" >
      <span className="h-12 w-0.5 rounded bg-purple-400/60" />
    </div>
    <div className="flex flex-col flex-1 min-w-0 min-h-[60vh] lg:min-h-0">
      {error && <div role="alert" className="p-3 text-sm text-red-200">{error} <button onClick={() => setError('')}>Dismiss</button></div>}
      {loading && <p role="status" className="p-3">Loading conversation?</p>}
      <DashboardPanel key={generation} location={location} uiLanguage={uiLanguage} activeSessionId={sessionId} onSelectSession={selectSession} onNewSession={reset}
        activeTab={activeTab} setActiveTab={setActiveTab} latestToolCalls={latestToolCalls} streamingEvent={streamingEvent} latestAdvisory={latestAdvisory}
        latestCalendar={latestCalendar} calendarError={calendarError} calendarRevision={calendarRevision} calendarDraft={liveTraces.findLast?.(trace => trace.tool === 'record_crop_schedule' && ['success', 'partial'].includes(trace.outputs?.status))?.outputs}
        latestAssistantMessage={latestAssistantMessage} farmerProfile={farmerProfile} onSaveProfile={saveProfile}
        onOpenAdvisory={adv => { setLatestAdvisory(adv); setActiveTab('advice') }} onDeleteAdvisory={id => { if (latestAdvisory?.id === id) setLatestAdvisory(null); setCalendarRevision(value => value + 1) }} />
    </div>
  </div>
}
