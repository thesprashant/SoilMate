import React, { useState, useRef, useEffect } from 'react'
import { Send, Mic, MicOff, Loader2 } from 'lucide-react'
import { uploadSpeechAudio } from '../services/api'
import { stopCurrentAudio } from '../utils/audioManager'

export default function ChatInput({ onSendMessage, language, placeholder, disabled, t }) {
  const [text, setText] = useState('')
  const [recording, setRecording] = useState(false)
  const [transcribing, setTranscribing] = useState(false)

  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])
  const mounted = useRef(true)
  const stopTimer = useRef(null)
  useEffect(() => () => {
    mounted.current = false; clearTimeout(stopTimer.current)
    const recorder = mediaRecorderRef.current
    if (recorder) { recorder.onstop = null; if (recorder.state !== 'inactive') recorder.stop(); recorder.stream.getTracks().forEach(t => t.stop()) }
  }, [])

  const quickChips = [
    { icon: '🌱', text: t?.promptPlant || 'What should I plant this season?' },
    { icon: '🌧️', text: t?.promptRain || 'Will it rain in the next 3 days?' },
    { icon: '💰', text: t?.promptMandi || 'What is the wheat mandi price nearby?' },
    { icon: '🧪', text: t?.promptSoil || 'Check soil pH and fertilizer advice' },
    { icon: '🐛', text: t?.promptPest || 'Pest risk for mustard & wheat' },
    { icon: '🏛️', text: t?.promptSubsidy || 'Government subsidy & PM-KISAN' }
  ]

  const handleSubmit = (e) => {
    e?.preventDefault()
    if (!text.trim() || disabled) return
    stopCurrentAudio()
    onSendMessage(text.trim())
    setText('')
  }

  const startRecording = async () => {
    stopCurrentAudio()
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (!mounted.current) { stream.getTracks().forEach(t => t.stop()); return }
      mediaRecorderRef.current = new MediaRecorder(stream)
      audioChunksRef.current = []

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorderRef.current.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: mediaRecorderRef.current.mimeType })
        setTranscribing(true)
        try {
          const res = await uploadSpeechAudio(audioBlob, language)
          if (!mounted.current) return
          if (res.text) {
            onSendMessage(res.text)
          } else {
            alert('Could not transcribe audio. Please try typing.')
          }
        } catch (err) {
          console.error('STT upload error:', err)
          alert('Speech-to-text service error. Please type your message.')
        } finally {
          setTranscribing(false)
          stream.getTracks().forEach((track) => track.stop())
        }
      }

      mediaRecorderRef.current.start()
      clearTimeout(stopTimer.current)
      stopTimer.current = setTimeout(() => { if (mediaRecorderRef.current?.state === 'recording') { mediaRecorderRef.current.stop(); setRecording(false) } }, 60000)
      setRecording(true)
    } catch (err) {
      console.error('Microphone access error:', err)
      alert('Microphone access denied or not supported in your browser.')
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current && recording) {
      mediaRecorderRef.current.stop()
      setRecording(false)
    }
  }

  const handleMicToggle = () => {
    if (recording) {
      stopRecording()
    } else {
      startRecording()
    }
  }

  return (
    <div className="space-y-2 p-3 bg-dark-900/90 border-t border-purple-500/20 backdrop-blur-md">
      {/* Quick Prompt Chips */}
      <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-none">
        {quickChips.map((chip, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => onSendMessage(chip.text)}
            disabled={disabled || recording}
            className="shrink-0 text-[11px] font-medium text-purple-200 bg-purple-950/60 hover:bg-purple-900/70 border border-purple-500/25 px-2.5 py-1 rounded-full transition disabled:opacity-50"
          >
            {chip.icon} {chip.text}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleMicToggle}
          disabled={disabled || transcribing}
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition ${
            recording
              ? 'bg-red-600 text-white animate-pulse shadow-lg'
              : 'bg-purple-950/60 text-purple-300 hover:bg-purple-900/60 border border-purple-500/30'
          }`}
          title={recording ? 'Stop recording' : 'Record voice note'}
        >
          {transcribing ? (
            <Loader2 size={18} className="animate-spin text-purple-300" />
          ) : recording ? (
            <MicOff size={18} />
          ) : (
            <Mic size={18} />
          )}
        </button>

        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={recording ? 'Recording audio note...' : (placeholder || 'Type your question in any Indian language...')}
          disabled={disabled || recording || transcribing}
          className="flex-1 rounded-xl border border-purple-500/30 bg-purple-950/40 px-3.5 py-2 text-xs sm:text-sm text-purple-100 placeholder-purple-400/50 outline-none focus:border-purple-400 transition"
        />

        <button
          type="submit"
          disabled={!text.trim() || disabled || recording || transcribing}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 text-white transition hover:from-purple-500 hover:to-indigo-500 disabled:opacity-40 shadow-glass"
          title="Send message"
        >
          <Send size={16} />
        </button>
      </form>
    </div>
  )
}
