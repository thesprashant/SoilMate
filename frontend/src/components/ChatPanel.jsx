import React, { useState, useRef, useEffect } from 'react'
import { Sprout, MessageSquare, X, ChevronUp, Plus } from 'lucide-react'
import VoiceAssistant from './VoiceAssistant'
import ChatMessages from './ChatMessages'
import ChatInput from './ChatInput'
import LanguageSelector from './LanguageSelector'
import LocationInput from './LocationInput'
import LiveProgressTicker from './LiveProgressTicker'
import useSpeech from '../hooks/useSpeech'
import useGeminiLive from '../hooks/useGeminiLive'
import { chatStream, chatSync } from '../services/api'
import { getUITranslations } from '../utils/translations'
import { stopCurrentAudio, playAudioBase64 } from '../utils/audioManager'

export default function ChatPanel({
  uiLanguage = 'hi',
  setUiLanguage,
  spokenLanguage = 'hi',
  setSpokenLanguage,
  location,
  setLocation,
  sessionId,
  setSessionId,
  messages,
  setMessages,
  onUserActivity,
  onNewSession,
  streamingEvent,
  setStreamingEvent,
  setFarmerProfile,
  liveTraces,
  setLiveTraces,
  ensureSession,
  disabled
}) {
  const [loading, setLoading] = useState(false)
  const [chatWindowOpen, setChatWindowOpen] = useState(false)
  const abortControllerRef = useRef(null)

  // Dynamic UI Translation dictionary for current UI Language
  const t = getUITranslations(uiLanguage)

  const [error, setError] = useState('')
  useEffect(() => () => { abortControllerRef.current?.abort(); stopCurrentAudio() }, [])
  const acceptProgress = ev => {
    setStreamingEvent(ev)
    if (ev.type === 'tool_end') setLiveTraces?.(previous => [...previous, { tool: ev.tool, inputs: ev.inputs || {}, outputs: ev.data, duration_ms: ev.duration_ms, summary: ev.message, status: ev.data?.error ? 'error' : 'success' }])
  }
  const geminiLive = useGeminiLive({
    uiLanguage: spokenLanguage, location, sessionId, ensureSession,
    onProgress: acceptProgress,
    onComplete: data => {
      setStreamingEvent(null)
      if (data.session_id) setSessionId(data.session_id)
      if (data.farmer_profile) setFarmerProfile?.(data.farmer_profile)
      const records = []
      if (data.user_content) records.push({ id: crypto.randomUUID(), role: 'user', content: data.user_content, language: data.language })
      if (data.content) records.push({ id: crypto.randomUUID(), role: 'assistant', content: data.content, language: data.language, tool_calls: data.tool_calls || [], advisory_id: data.advisory_id })
      setMessages(previous => [...previous, ...records]); setLiveTraces?.([])
    },
    onError: err => { setError(err.message); setStreamingEvent(null) }
  })
  const handleSendMessage = async text => {
    if (!text.trim() || disabled || loading) return
    stopCurrentAudio(); geminiLive.disconnectLive(); abortControllerRef.current?.abort()
    const controller = new AbortController(); abortControllerRef.current = controller
    setError(''); setLoading(true); onUserActivity?.()
    try {
      const sid = await ensureSession()
      if (controller.signal.aborted) return
      setMessages(previous => [...previous, { id: crypto.randomUUID(), role: 'user', content: text, language: spokenLanguage }])
      await chatStream({ message: text, sessionId: sid, language: spokenLanguage, location, voiceOutput: true, signal: controller.signal }, {
        onProgress: ev => { if (!controller.signal.aborted) acceptProgress(ev) },
        onComplete: data => {
          if (controller.signal.aborted) return
          if (data.language) setSpokenLanguage?.(data.language)
          if (data.farmer_profile) setFarmerProfile?.(data.farmer_profile)
          setMessages(previous => [...previous, { id: crypto.randomUUID(), role: 'assistant', content: data.response, content_english: data.response_english, language: data.language, audio_base64: data.audio_base64, tool_calls: data.tool_calls || [], advisory_id: data.advisory_id }])
          setLiveTraces?.([])
          if (data.audio_base64) playAudioBase64(data.audio_base64)
        },
        onError: err => { if (!controller.signal.aborted) setError(err.message) }
      })
    } catch (err) { if (!controller.signal.aborted) setError(err.message) }
    finally { if (!controller.signal.aborted) { setLoading(false); setStreamingEvent(null) } }
  }

  // Voice speech hook uses the active spokenLanguage
  const speech = useSpeech(spokenLanguage, (transcript) => {
    handleSendMessage(transcript, true)
  })

  const isLiveActive = geminiLive.active || geminiLive.connecting

  // Trigger tab switch when user starts speech listening
  const handleOrbToggle = () => {
    // Silence audio immediately upon tapping to talk
    stopCurrentAudio()
    onUserActivity?.()
    if (disabled) return
    abortControllerRef.current?.abort()
    setLoading(false)
    geminiLive.toggleLive()
  }

  const liveSpeechProxy = {
    listening: isLiveActive,
    speaking: geminiLive.speaking,
    interim: geminiLive.connecting
      ? (t?.connecting || "Connecting Live...")
      : geminiLive.speaking
      ? (t?.speakToInterrupt || "SoilMate is speaking (speak to interrupt)...")
      : geminiLive.liveTranscript
      ? geminiLive.liveTranscript
      : (t?.listening || "Listening... Speak naturally"),
    error: geminiLive.error,
    toggle: handleOrbToggle,
    clearError: geminiLive.clearError
  }

  const handleNewSessionAction = () => {
    stopCurrentAudio()
    geminiLive.disconnectLive()
    onNewSession?.()
  }


  const latestMessage = messages[messages.length - 1]

  return (
    <aside className="relative flex flex-col h-[75vh] min-h-[520px] lg:h-full w-full border-r border-purple-500/20 bg-[#07040D] shrink-0 overflow-hidden">
      {error && <div role="alert" className="p-3 text-sm text-red-200">{error} <button onClick={() => setError('')}>Dismiss</button></div>}
      {chatWindowOpen ? (
        /* ================= FULL CHAT VIEW (COVERS TALK BUTTON, 100% OPAQUE) ================= */
        <div className="flex-1 flex flex-col h-full w-full bg-[#07040D] overflow-hidden">
          {/* Dedicated Chat Header with Cross Button */}
          <header className="p-3.5 border-b border-purple-500/25 flex items-center justify-between bg-dark-900/90 shrink-0">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-purple-700 to-indigo-600 text-white shadow-glass">
                <MessageSquare size={18} />
              </div>
              <div>
                <h2 className="text-sm font-bold text-white leading-tight">
                  {t.chatTitle}
                </h2>
                <span className="text-[11px] text-purple-300/70">
                  {messages.length} {t.chatMessagesCount}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleNewSessionAction}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-purple-900/40 border border-purple-500/30 text-purple-200 hover:text-white hover:bg-purple-800/60 transition shadow-glass text-xs font-semibold cursor-pointer"
                title={t.newSession || "New Session"}
              >
                <Plus size={14} className="text-cyan-400" />
                <span className="hidden sm:inline">{t.newSession || "New Session"}</span>
              </button>

              {/* Cross Button to return to Voice Orb Screen */}
              <button
                onClick={() => {
                  stopCurrentAudio()
                  setChatWindowOpen(false)
                }}
                className="flex h-8 w-8 items-center justify-center rounded-xl bg-purple-950 border border-purple-500/30 text-purple-200 hover:text-white hover:bg-purple-900 transition shadow-glass cursor-pointer"
                title="Close and return to talk button"
              >
                <X size={18} />
              </button>
            </div>
          </header>

          {/* Compact context pill row inside chat */}
          <div className="px-3.5 py-1.5 border-b border-purple-500/15 bg-dark-950/60 flex items-center justify-between gap-2 shrink-0">
            <div className="flex-1 min-w-0">
              <LanguageSelector value={uiLanguage} onChange={setUiLanguage} label={t.uiLangLabel} />
            </div>
            <div className="flex-1 min-w-0">
              <LocationInput location={location} onLocationChange={setLocation} t={t} />
            </div>
          </div>

          {/* Scrollable Chat Messages */}
          <div className="flex-1 overflow-hidden flex flex-col">
            <ChatMessages
              messages={messages}
              streamingEvent={streamingEvent}
              liveTraces={liveTraces}
              loading={loading}
              t={t}
            />

            {/* Chat Typing Input */}
            <ChatInput
              onSendMessage={(txt) => handleSendMessage(txt, false)}
              language={spokenLanguage}
              placeholder={t.typePlaceholder}
              disabled={loading || disabled || isLiveActive}
              t={t}
            />
          </div>
        </div>
      ) : (
        /* ================= VOICE ORB VIEW ================= */
        <div className="flex-1 flex flex-col h-full w-full bg-[#07040D] overflow-hidden">
          {/* Top Header */}
          <header className="p-3.5 border-b border-purple-500/20 space-y-2.5 bg-dark-950/80 shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-purple-700 to-indigo-600 text-white shadow-glass">
                  <Sprout size={20} />
                </div>
                <div>
                  <h1 className="text-base font-extrabold text-white leading-tight flex items-center gap-1.5">
                    {t.appTitle}
                    <span className="text-[10px] font-medium text-purple-300 bg-purple-900/60 px-2 py-0.5 rounded-full border border-purple-500/30">
                      {t.appBadge}
                    </span>
                  </h1>
                  <p className="text-[11px] text-purple-300/70 font-medium">{t.appSubtitle}</p>
                </div>
              </div>

              <button
                type="button"
                onClick={handleNewSessionAction}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-purple-900/40 border border-purple-500/30 text-purple-200 hover:text-white hover:bg-purple-800/60 transition shadow-glass text-xs font-semibold cursor-pointer"
                title={t.newSession || "New Session"}
              >
                <Plus size={14} className="text-cyan-400" />
                <span className="hidden sm:inline">{t.newSession || "New Session"}</span>
              </button>
            </div>

            {/* Controls: UI Language and Location */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <LanguageSelector value={uiLanguage} onChange={setUiLanguage} label={t.uiLangLabel} />
              <LocationInput location={location} onLocationChange={setLocation} t={t} />
            </div>
          </header>

          {/* Center: Push-to-Talk Animated 3D Glowing Mesh Orb */}
          <div className="flex-1 flex flex-col items-center justify-center p-4 overflow-hidden">
            <VoiceAssistant
              speech={liveSpeechProxy}
              t={t}
            />
          </div>

          {/* Bottom: Clickable Live Transcript Banner */}
          <div className="p-4 pt-1 pb-3 shrink-0">
            {isLiveActive ? (
              <div
                onClick={() => setChatWindowOpen(true)}
                className="w-full cursor-pointer rounded-2xl border-2 border-cyan-400 bg-dark-900 p-3.5 shadow-[0_0_30px_rgba(56,189,248,0.4)] transition hover:border-cyan-300 group"
              >
                <div className="flex items-center justify-between text-xs text-cyan-300 font-bold mb-1">
                  <span className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping" />
                    {geminiLive.speaking ? (t?.speaking || "SoilMate Speaking...") : (t?.liveTranscript || "Live Voice")}
                  </span>
                  <span className="text-[10px] text-purple-300 group-hover:text-white">
                    {t.clickToChat}
                  </span>
                </div>
                <p className="text-sm font-bold live-highlight tracking-wide leading-relaxed min-h-[24px]">
                  {liveSpeechProxy.interim}
                </p>
              </div>
            ) : streamingEvent ? (
              <div
                onClick={() => setChatWindowOpen(true)}
                className="w-full cursor-pointer transition hover:opacity-90"
              >
                <LiveProgressTicker event={streamingEvent} />
              </div>
            ) : (
              <div
                onClick={() => setChatWindowOpen(true)}
                className="w-full cursor-pointer rounded-2xl border border-purple-500/25 bg-dark-850 p-3.5 shadow-glass hover:border-purple-400/50 transition group"
              >
                <div className="flex items-center justify-between text-xs text-purple-300 font-semibold mb-1">
                  <span className="flex items-center gap-1.5">
                    <MessageSquare size={13} className="text-purple-400" />
                    {latestMessage ? (latestMessage.role === 'user' ? (t.you ? `${t.you}:` : 'You:') : (t.appTitle ? `${t.appTitle}:` : 'SoilMate:')) : t.chatTitle}
                  </span>
                  <span className="text-[10px] text-purple-400 group-hover:text-white flex items-center gap-0.5">
                    {t.clickToChat} ({messages.length}) <ChevronUp size={12} />
                  </span>
                </div>
                <p className="text-xs text-stone-200 line-clamp-2 leading-relaxed">
                  {latestMessage ? latestMessage.content : t.tapToSpeak}
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  )
}
