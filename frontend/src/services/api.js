// ===== SOILMATE REAL-TIME API CLIENT =====
// Connects directly to FastAPI and preserves explicit provider failure states.

export const BASE = import.meta.env?.VITE_API_BASE_URL || '/api'

async function request(path, options = {}) {
  const url = `${BASE}${path}`
  const headers = options.headers || {}
  
  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }

  const res = await fetch(url, { credentials: 'include', signal: AbortSignal.timeout(30000), ...options, headers })
  if (!res.ok) {
    let errorDetail = `Request failed (${res.status})`
    try {
      const errJson = await res.json()
      if (errJson.detail) errorDetail = typeof errJson.detail === 'string' ? errJson.detail : 'Invalid input. Check the entered values.'
    } catch (_) {}
    throw new Error(errorDetail)
  }
  return res.json()
}

/** Check backend health and API key readiness */
export async function checkHealth() {
  return request('/health')
}

/** Synchronous Chat Turn (POST /api/chat) */
export async function chatSync({ message, sessionId, language, location, voiceOutput = true }) {
  return request('/chat', {
    method: 'POST',
    body: JSON.stringify({
      message,
      session_id: sessionId || null,
      language: language || null,
      location: location || null,
      voice_output: voiceOutput
    })
  })
}

/**
 * Server-Sent Events (SSE) Streaming Chat (POST /api/chat/stream)
 * Streams real-time progress events ('thinking', 'tool_start', 'tool_end', 'synthesizing', etc.)
 * followed by the final completion event.
 */
export async function chatStream(
  { message, sessionId, language, location, voiceOutput = true, signal },
  { onProgress, onComplete, onError }
) {
  const url = `${BASE}/chat/stream`
  try {
    const res = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      signal,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream'
      },
      body: JSON.stringify({
        request_id: crypto.randomUUID(),
        message,
        session_id: sessionId || null,
        language: language || null,
        location: location || null,
        voice_output: voiceOutput
      })
    })

    if (!res.ok) {
      let detail = `Stream request failed (${res.status})`
      try {
        const j = await res.json()
        if (j.detail) detail = j.detail
      } catch (_) {}
      throw new Error(detail)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let completed = false

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        if (!completed) throw new Error('Connection ended before the answer completed. Reload history before retrying.')
        break
      }

      buffer += decoder.decode(value, { stream: true })
      buffer = buffer.replace(/\r\n/g, '\n')
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || '' // Keep unfinished chunk in buffer

      for (const block of lines) {
        if (!block.trim()) continue
        const eventMatch = block.match(/event:\s*([^\n]+)/)
        const dataMatch = block.match(/data:\s*([\s\S]+)$/)

        if (eventMatch && dataMatch) {
          const eventType = eventMatch[1].trim()
          const parsedData = JSON.parse(dataMatch[1].trim())
          if (eventType === 'progress') onProgress?.(parsedData)
          else if (eventType === 'complete') {
            completed = true
            await reader.cancel()
            onComplete?.(parsedData)
            return
          } else if (eventType === 'error') {
            completed = true
            await reader.cancel()
            throw new Error(parsedData.message || 'Stream error')
          }
        }
      }
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      // User aborted/interrupted in favor of new question - ignore cleanly
      return
    }
    if (onError) onError(err)
    else throw err
  }
}

/** Retrieve previous chat history for a session */
export async function fetchChatHistory(sessionId) {
  if (!sessionId) return []
  return request(`/chat/history/${encodeURIComponent(sessionId)}`)
}

/** List recent sessions */
export async function fetchSessions(limit = 20) {
  return request(`/sessions?limit=${limit}`)
}

/** Get detail of a specific session with farmer profile */
export async function fetchSessionDetail(sessionId) {
  if (!sessionId) return null
  return request(`/sessions/${encodeURIComponent(sessionId)}`)
}

/** Delete a session and its associated chat history */
export async function deleteSessionApi(sessionId) {
  if (!sessionId) return
  return request(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE'
  })
}

/** List saved crop advisories & schedules */
export async function fetchAdvisories({ sessionId, crop, limit = 20 } = {}) {
  const params = new URLSearchParams()
  if (sessionId) params.append('session_id', sessionId)
  if (crop) params.append('crop', crop)
  if (limit) params.append('limit', limit)
  return request(`/advisories?${params.toString()}`)
}

/** Get full details of a specific advisory */
export async function fetchAdvisoryDetail(id) {
  return request(`/advisories/${encodeURIComponent(id)}`)
}

/** Delete a saved crop advisory */
export async function deleteAdvisoryApi(advisoryId) {
  if (!advisoryId) return
  return request(`/advisories/${encodeURIComponent(advisoryId)}`, {
    method: 'DELETE'
  })
}

/** Fetch live 7-day weather from Open-Meteo */
export async function fetchLiveWeather(lat, lon) {
  return request(`/weather?lat=${lat}&lon=${lon}`)
}

/** Fetch live soil analysis from SoilGrids */
export async function fetchLiveSoil(lat, lon) {
  return request(`/soil?lat=${lat}&lon=${lon}`)
}

/** Fetch live mandi rates from Agmarknet */
export async function fetchLiveMandi(state, commodity) {
  const params = new URLSearchParams({ commodity })
  if (state) params.append('state', state)
  return request(`/mandi?${params.toString()}`)
}

/** Search place coordinates */
export async function geocodePlace(query) {
  return request(`/geocode?query=${encodeURIComponent(query)}`)
}

/** Speech-to-Text: Upload audio blob */
export async function uploadSpeechAudio(audioBlob, language = null) {
  const fd = new FormData()
  const extension = audioBlob.type.includes('webm') ? 'webm' : audioBlob.type.includes('mp4') ? 'mp4' : audioBlob.type.includes('ogg') ? 'ogg' : 'wav'
  fd.append('file', audioBlob, `speech.${extension}`)
  if (language) fd.append('language', language)
  return request('/voice/stt', { method: 'POST', body: fd })
}

/** Text-to-Speech: Synthesize text into voice */
export async function synthesizeSpeech(text, language = 'hi') {
  return request('/voice/tts', {
    method: 'POST',
    body: JSON.stringify({ text, language })
  })
}

export const createSession = () => request('/sessions', { method: 'POST' })
export const fetchCalendars = (limit = 50) => request(`/calendars?limit=${limit}`)
export const updateProfile = (id, profile) => request(`/sessions/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(profile) })
export function liveSocketUrl() {
  const url = new URL(`${BASE.replace(/\/$/, '')}/ws/live`, window.location.href)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}
