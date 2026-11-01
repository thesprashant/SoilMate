import { useState, useRef, useCallback, useEffect } from 'react'
import { stopCurrentAudio } from '../utils/audioManager'
import { liveSocketUrl } from '../services/api'

/**
 * useGeminiLive: Real-Time Multimodal Voice & Audio WebSocket Hook
 * Connects directly to SoilMate Gemini Live WebSocket backend bridge.
 * Features:
 * - Sub-second latency (~400ms) full-duplex speech-to-speech.
 * - Raw 16kHz PCM streaming from browser microphone to Gemini.
 * - Raw 24kHz PCM native audio playback from Gemini with zero-gap scheduling.
 * - Instant real-time barge-in (interruption) when user speaks or stops.
 * - Live autonomous tool execution streaming (Open-Meteo, SoilGrids, Mandi).
 */
export default function useGeminiLive({
  uiLanguage = 'hi',
  location = null,
  sessionId = null,
  onProgress,
  onComplete,
  onError,
  onTextChunk,
  ensureSession
}) {
  const [active, setActive] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [liveTranscript, setLiveTranscript] = useState('')
  const [error, setError] = useState('')

  const wsRef = useRef(null)
  const connectionVersion = useRef(0)
  const callbacks = useRef({})
  callbacks.current = { onProgress, onComplete, onError, onTextChunk }
  const micAudioCtxRef = useRef(null)
  const micStreamRef = useRef(null)
  const processorRef = useRef(null)

  const playAudioCtxRef = useRef(null)
  const nextPlayTimeRef = useRef(0)
  const activeSourcesRef = useRef([])

  const currentModelTextRef = useRef('')

  // Stop and cancel all queued and playing audio
  const stopPlayback = useCallback(() => {
    activeSourcesRef.current.forEach((src) => {
      try {
        src.stop()
        src.disconnect()
      } catch (_) {}
    })
    activeSourcesRef.current = []
    if (playAudioCtxRef.current) {
      nextPlayTimeRef.current = playAudioCtxRef.current.currentTime
    }
    setSpeaking(false)
  }, [])

  // Play a base64 encoded 24kHz 16-bit mono PCM chunk
  const playPcmChunk = useCallback((b64Pcm) => {
    try {
      if (!playAudioCtxRef.current) {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext
        playAudioCtxRef.current = new AudioContextClass({ sampleRate: 24000 })
      }
      const ctx = playAudioCtxRef.current
      if (ctx.state === 'suspended') {
        ctx.resume()
      }

      // Base64 to ArrayBuffer
      const binaryString = window.atob(b64Pcm)
      const len = binaryString.length
      const bytes = new Uint8Array(len)
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i)
      }

      // Convert 16-bit PCM little-endian to Float32 (-1.0 to 1.0)
      const numSamples = Math.floor(bytes.length / 2)
      const floats = new Float32Array(numSamples)
      const dataView = new DataView(bytes.buffer)

      for (let i = 0; i < numSamples; i++) {
        const int16 = dataView.getInt16(i * 2, true)
        floats[i] = int16 < 0 ? int16 / 32768.0 : int16 / 32767.0
      }

      const audioBuffer = ctx.createBuffer(1, numSamples, 24000)
      audioBuffer.copyToChannel(floats, 0)

      const source = ctx.createBufferSource()
      source.buffer = audioBuffer
      source.connect(ctx.destination)

      const now = ctx.currentTime
      const startTime = Math.max(now, nextPlayTimeRef.current)
      source.start(startTime)
      nextPlayTimeRef.current = startTime + audioBuffer.duration

      activeSourcesRef.current.push(source)
      setSpeaking(true)

      source.onended = () => {
        activeSourcesRef.current = activeSourcesRef.current.filter((s) => s !== source)
        if (activeSourcesRef.current.length === 0) {
          setSpeaking(false)
        }
      }
    } catch (err) {
      console.error('[GeminiLive] Error playing PCM chunk:', err)
    }
  }, [])

  // Start microphone capture and 16kHz PCM streaming
  const startMicCapture = useCallback(async (ws) => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      })
      // Permission can resolve after the user ends or replaces the call.
      if (wsRef.current !== ws || ws.readyState !== WebSocket.OPEN) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      micStreamRef.current = stream

      const AudioContextClass = window.AudioContext || window.webkitAudioContext
      const micCtx = new AudioContextClass({ sampleRate: 16000 })
      if (micCtx.state === 'suspended') {
        await micCtx.resume()
      }
      if (wsRef.current !== ws || ws.readyState !== WebSocket.OPEN) {
        stream.getTracks().forEach(track => track.stop()); await micCtx.close(); return
      }
      micAudioCtxRef.current = micCtx

      const sourceNode = micCtx.createMediaStreamSource(stream)
      // Buffer size 4096 gives ~256ms frames; 2048 gives ~128ms frames
      const processor = micCtx.createScriptProcessor(2048, 1, 1)
      processorRef.current = processor

      processor.onaudioprocess = (e) => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return
        const inputData = e.inputBuffer.getChannelData(0)

        // Convert Float32Array to 16-bit PCM integer
        const pcm16 = new Int16Array(inputData.length)
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]))
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
        }

        // Convert Int16Array to base64
        const bytes = new Uint8Array(pcm16.buffer)
        let binary = ''
        const chunkSize = 8192
        for (let i = 0; i < bytes.length; i += chunkSize) {
          binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize))
        }
        const base64 = window.btoa(binary)

        // Stream audio chunk to backend WebSocket
        try {
          ws.send(JSON.stringify({ type: 'audio', data: base64 }))
        } catch (_) {}
      }

      sourceNode.connect(processor)
      processor.connect(micCtx.destination)
    } catch (err) {
      if (wsRef.current !== ws) return
      console.error('[GeminiLive] Mic access error:', err)
      setError(err.message || 'Could not access the microphone.')
      callbacks.current.onError?.(err)
      disconnectLive()
    }
  }, [])

  // Clean up mic capture
  const stopMicCapture = useCallback(() => {
    if (processorRef.current) {
      try {
        processorRef.current.disconnect()
      } catch (_) {}
      processorRef.current = null
    }
    if (micAudioCtxRef.current) {
      try {
        micAudioCtxRef.current.close()
      } catch (_) {}
      micAudioCtxRef.current = null
    }
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((track) => track.stop())
      micStreamRef.current = null
    }
  }, [])

  // Connect to Gemini Live WebSocket
  const connectLive = useCallback(async () => {
    if (wsRef.current) return
    stopCurrentAudio()
    stopPlayback()

    setConnecting(true)
    setError('')
    setLiveTranscript('')
    currentModelTextRef.current = ''

    const attempt = ++connectionVersion.current
    let pingTimer = null
    try {
      const activeSession = await ensureSession()
      if (attempt !== connectionVersion.current) return
      const wsUrl = liveSocketUrl()
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = async () => {
        if (wsRef.current !== ws) { ws.close(); return }
        // Send initial session handshake
        ws.send(
          JSON.stringify({
            type: 'init',
            session_id: activeSession,
            language: uiLanguage,
            location: location || null
          })
        )
        // Keepalive ping every 10 seconds to maintain persistent bidirectional stream
        pingTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            try {
              ws.send(JSON.stringify({ type: 'ping' }))
            } catch (_) {}
          }
        }, 10000)
      }

      ws.onmessage = (event) => {
        if (wsRef.current !== ws) return
        try {
          const msg = JSON.parse(event.data)

          if (msg.type === 'ready') {
            setConnecting(false)
            setActive(true)
            startMicCapture(ws)
          } else if (msg.type === 'audio') {
            // Real-time 24kHz PCM audio chunk from Gemini
            playPcmChunk(msg.data)
          } else if (msg.type === 'user_text') {
            setLiveTranscript(msg.text)
          } else if (msg.type === 'text') {
            // Streaming text chunk from Gemini
            currentModelTextRef.current += msg.text
            setLiveTranscript(currentModelTextRef.current)
            callbacks.current.onTextChunk?.(msg.text, currentModelTextRef.current)
          } else if (msg.type === 'interrupted') {
            // Instant barge-in: farmer spoke while Gemini was talking
            stopPlayback()
          } else if (msg.type === 'tool_start') {
            callbacks.current.onProgress?.({
              type: 'tool_start',
              tool: msg.tool,
              message: msg.summary || `Running ${msg.tool}...`,
              inputs: msg.args
            })
          } else if (msg.type === 'tool_end') {
            callbacks.current.onProgress?.({
              type: 'tool_end',
              tool: msg.tool,
              message: msg.summary || `${msg.tool} completed`,
              data: msg.data,
              duration_ms: msg.duration_ms,
              inputs: msg.inputs
            })
          } else if (msg.type === 'turn_complete') {
            const finalReply = currentModelTextRef.current
            currentModelTextRef.current = ''
            callbacks.current.onComplete?.({
              session_id: msg.session_id,
              farmer_profile: msg.farmer_profile,
              content: msg.content || finalReply,
              user_content: msg.user_content,
              language: msg.language,
              tool_calls: msg.tool_calls || [],
              advisory_id: msg.advisory_id
            })
          } else if (msg.type === 'error') {
            console.error('[GeminiLive] Server error:', msg.message)
            setError(msg.message || 'Live voice connection failed.')
            callbacks.current.onError?.(new Error(msg.message))
            disconnectLive()
          }
        } catch (e) {
          console.error('[GeminiLive] Parse error:', e)
        }
      }

      ws.onerror = (e) => {
        if (pingTimer) clearInterval(pingTimer)
        if (wsRef.current !== ws) return
        console.warn('[GeminiLive] WebSocket error:', e)
        setError('Live voice connection failed. Check that the backend is running.')
        callbacks.current.onError?.(new Error('WebSocket connection error'))
        disconnectLive()
      }

      ws.onclose = (e) => {
        if (pingTimer) clearInterval(pingTimer)
        if (wsRef.current !== ws) return
        console.log('[GeminiLive] WebSocket closed, code:', e?.code, 'reason:', e?.reason)
        disconnectLive()
      }
    } catch (err) {
      if (attempt !== connectionVersion.current) return
      console.error('[GeminiLive] Connection failure:', err)
      setConnecting(false)
      setError(err.message || 'Could not connect to live voice.')
      callbacks.current.onError?.(err)
    }
  }, [sessionId, uiLanguage, location, startMicCapture, playPcmChunk, stopPlayback, onProgress, onComplete, onError, onTextChunk, ensureSession])

  // Disconnect and reset
  const disconnectLive = useCallback(() => {
    connectionVersion.current += 1
    stopMicCapture()
    stopPlayback()
    if (wsRef.current) {
      try {
        wsRef.current.close()
      } catch (_) {}
      wsRef.current = null
    }
    if (playAudioCtxRef.current) { playAudioCtxRef.current.close().catch(() => {}); playAudioCtxRef.current = null }
    nextPlayTimeRef.current = 0
    setActive(false)
    setConnecting(false)
  }, [stopMicCapture, stopPlayback])

  // Toggle live session on Orb click
  const toggleLive = useCallback(() => {
    if (active || connecting) {
      disconnectLive()
    } else {
      connectLive()
    }
  }, [active, connecting, connectLive, disconnectLive])

  // Send a text message over the live WebSocket
  const sendTextMessage = useCallback((text) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      stopPlayback()
      wsRef.current.send(JSON.stringify({ type: 'text', text }))
    }
  }, [stopPlayback])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnectLive()
    }
  }, [disconnectLive])

  return {
    active,
    connecting,
    speaking,
    liveTranscript,
    error,
    clearError: () => setError(''),
    toggleLive,
    connectLive,
    disconnectLive,
    sendTextMessage
  }
}

