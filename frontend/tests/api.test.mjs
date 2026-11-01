import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chatStream, liveSocketUrl, uploadSpeechAudio } from '../src/services/api.js'

function response(chunks) {
  return new Response(new ReadableStream({ start(controller) {
    for (const chunk of chunks) controller.enqueue(chunk)
    controller.close()
  }}))
}
const encode = text => new TextEncoder().encode(text)

test('SSE preserves split multilingual text and advisory identity', async () => {
  const bytes = encode('event: progress\r\ndata: {"type":"thinking","message":"काम"}\r\n\r\nevent: complete\r\ndata: {"response":"नमस्ते","advisory_id":"adv_1"}\r\n\r\n')
  globalThis.fetch = async () => response([...bytes].map(b => new Uint8Array([b])))
  let result, events = []
  await chatStream({ message: 'test' }, { onProgress: e => events.push(e), onComplete: e => { result = e }, onError: e => { throw e } })
  assert.equal(result.response, 'नमस्ते')
  assert.equal(result.advisory_id, 'adv_1')
  assert.equal(events[0].message, 'काम')
})

test('truncated stream reports failure without retrying the request', async () => {
  let requests = 0, error
  globalThis.fetch = async () => { requests++; return response([encode('event: progress\ndata: {"type":"thinking"}\n\n')]) }
  await chatStream({ message: 'test' }, { onError: e => { error = e } })
  assert.match(error.message, /before the answer completed/)
  assert.equal(requests, 1)
})

test('provider error reaches UI once', async () => {
  let errors = []
  globalThis.fetch = async () => response([encode('event: error\ndata: {"message":"Unavailable"}\n\n')])
  await chatStream({ message: 'test' }, { onError: e => errors.push(e) })
  assert.equal(errors.length, 1)
  assert.equal(errors[0].message, 'Unavailable')
})

test('intentional cancellation does not show an error', async () => {
  globalThis.fetch = async () => { throw new DOMException('cancelled', 'AbortError') }
  await chatStream({ message: 'test' }, { onError: () => assert.fail('Cancellation reported as failure') })
})

test('voice upload retains actual recording format', async () => {
  globalThis.fetch = async (url, opts) => {
    assert.equal(opts.body.get('file').name, 'speech.webm')
    assert.equal(opts.body.get('file').type, 'audio/webm')
    return Response.json({ text: 'hello' })
  }
  await uploadSpeechAudio(new Blob(['test'], { type: 'audio/webm' }), 'en')
})

test('websocket uses the same origin and API base as HTTP', () => {
  globalThis.window = { location: { href: 'https://soilmate.example/' } }
  assert.equal(liveSocketUrl(), 'wss://soilmate.example/api/ws/live')
})
