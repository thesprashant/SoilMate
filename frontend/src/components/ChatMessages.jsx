import React, { useEffect, useRef, useState } from 'react'
import { Sprout, User, Volume2, Globe, Sparkles } from 'lucide-react'
import { playAudioBase64, stopCurrentAudio } from '../utils/audioManager'
import AgentTraceView from './AgentTraceView'

function MessageItem({ m, t }) {
  const isUser = m.role === 'user'
  const [showEnglish, setShowEnglish] = useState(false)
  const [playing, setPlaying] = useState(false)

  const playAudio = () => {
    if (!m.audio_base64) return
    setPlaying(true)
    playAudioBase64(
      m.audio_base64,
      () => setPlaying(false),
      () => setPlaying(false)
    )
  }

  return (
    <div className={`flex gap-2.5 ${isUser ? 'flex-row-reverse' : 'flex-row'} my-2`}>
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl shadow-md ${
          isUser
            ? 'bg-purple-600 text-white border border-purple-400/30'
            : 'bg-gradient-to-br from-purple-800 to-indigo-900 text-purple-200 border border-purple-500/30'
        }`}
      >
        {isUser ? <User size={16} /> : <Sprout size={16} />}
      </div>

      <div className={`flex max-w-[88%] flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={`rounded-2xl px-3.5 py-2.5 text-xs sm:text-sm leading-relaxed shadow-glass ${
            isUser
              ? 'rounded-tr-xs bg-gradient-to-r from-purple-600 to-indigo-700 text-white border border-purple-400/30'
              : 'rounded-tl-xs bg-dark-850/90 text-stone-100 border border-purple-500/20 backdrop-blur-md'
          }`}
        >
          <div className="whitespace-pre-wrap">{m.content}</div>

          {!isUser && m.content_english && m.content_english !== m.content && (
            <div className="mt-2 pt-2 border-t border-purple-500/15">
              <button
                onClick={() => setShowEnglish(!showEnglish)}
                className="text-[11px] font-semibold text-purple-300 hover:text-white flex items-center gap-1 transition cursor-pointer"
              >
                <Globe size={11} />
                {showEnglish ? (t?.hideEnglish || 'Hide English translation') : (t?.viewEnglish || 'View English translation')}
              </button>
              {showEnglish && (
                <p className="mt-1 text-xs text-purple-200/90 italic bg-purple-950/50 p-2 rounded-lg border border-purple-500/20">
                  {m.content_english}
                </p>
              )}
            </div>
          )}

          {!isUser && m.audio_base64 && (
            <div className="mt-2 pt-1 flex items-center gap-2">
              <button
                onClick={playAudio}
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold transition ${
                  playing
                    ? 'bg-purple-600 text-white animate-pulse shadow-orb'
                    : 'bg-purple-900/40 text-purple-200 hover:bg-purple-800/60 border border-purple-500/30'
                }`}
              >
                <Volume2 size={13} />
                {playing ? (t?.playingVoice || 'Playing Voice...') : (t?.listenNativeVoice || 'Listen in Native Voice')}
              </button>
            </div>
          )}

          {!isUser && m.tool_calls?.length > 0 && <div className="mt-3"><AgentTraceView toolCalls={m.tool_calls} t={t} /></div>}

        </div>

        <span className="text-[10px] text-purple-400/60 font-medium px-1">
          {isUser ? (t?.you || 'You') : (t?.appTitle || 'SoilMate')} · {new Date(m.created_at || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          {m.language && <span className="ml-1 uppercase text-purple-300/80">[{m.language}]</span>}
        </span>
      </div>
    </div>
  )
}

export default function ChatMessages({ messages, streamingEvent, liveTraces, loading, t }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingEvent, loading])

  return (
    <div className="flex-1 overflow-y-auto px-3 py-2 scroll-thin space-y-1">
      {messages.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-48 text-center text-purple-300/50 space-y-1">
          <p className="text-xs">{t?.noChatHistory || 'No chat history yet.'}</p>
          <p className="text-[11px]">{t?.startChatPrompt || 'Speak or type your question to start.'}</p>
        </div>
      ) : (
        messages.map((m, idx) => (
          <MessageItem key={m.id || idx} m={m} t={t} />
        ))
      )}
      {liveTraces?.length > 0 && <div className="ml-10 my-3"><AgentTraceView toolCalls={liveTraces} t={t} /></div>}
      {streamingEvent?.type === 'tool_start' && <p role="status" className="ml-10 my-2 text-xs text-cyan-300">{streamingEvent.message || 'Fetching data…'}</p>}
      <div ref={bottomRef} />
    </div>
  )
}
