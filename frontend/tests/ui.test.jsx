import React from 'react'
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { renderToStaticMarkup } from 'react-dom/server'
import SchedulePanel from '../src/components/SchedulePanel'
import AdvicePanel from '../src/components/AdvicePanel'
import AgentTraceView from '../src/components/AgentTraceView'

test('missing schedule never produces default crop timings', () => {
  const html = renderToStaticMarkup(<SchedulePanel advisory={{ crop_name: 'Cotton' }} />)
  assert.match(html, /No schedule yet/)
  assert.doesNotMatch(html, /110-120|20-25|Crown Root/)
})

test('persisted schedule renders its actual stages and source', () => {
  const html = renderToStaticMarkup(<SchedulePanel advisory={{ crop_name: 'Rice', evidence: { schedule: [{ stage: 'sowing', date: '2026-11-10', guidance: 'Verified regional window', quote: 'Supporting excerpt', source: 'https://agritech.tnau.ac.in/reference', retrieved_at: '2026-11-01' }] } }} />)
  assert.match(html, /Verified regional window/)
  assert.match(html, /2026-11-10/)
  assert.match(html, /https:\/\/agritech.tnau.ac.in\/reference/)
})

test('advice presents the response without technical source payloads', () => {
  const html = renderToStaticMarkup(<AdvicePanel advisory={{ crop_name: 'Rice', full_advisory_text: 'Check soil first', evidence: { tools: [{ tool: 'get_soil_data', outputs: { error: 'Coverage unavailable', source: 'https://rest.isric.org' } }] } }} />)
  assert.match(html, /Check soil first/)
  assert.doesNotMatch(html, /Sources and limitations|Coverage unavailable/)
})

test('chat tool activity shows status without request or response', () => {
  const html = renderToStaticMarkup(<AgentTraceView toolCalls={[{ tool: 'get_soil_data', status: 'success', inputs: { latitude: 20 }, outputs: { ph: 7.5 } }]} />)
  assert.match(html, /SoilGrids/)
  assert.match(html, /Successful/)
  assert.doesNotMatch(html, /7\.5|latitude|Full request|Result/)
})

test('calendar shows a date and task table', () => {
  const html = renderToStaticMarkup(<SchedulePanel />)
  assert.match(html, /No schedule yet/)
  assert.match(html, /<th[^>]*>Date<\/th>/)
  assert.match(html, /<th[^>]*>Task<\/th>/)
})

test('calendar displays source-supported relative sowing intervals', () => {
  const html = renderToStaticMarkup(<SchedulePanel advisory={{ crop_name: 'wheat', evidence: { schedule: [{ guidance: 'Irrigate at crown root stage', days_after_sowing: 15, days_after_sowing_end: 20 }] } }} />)
  assert.match(html, /15–20 days after sowing/)
  assert.match(html, /Irrigate at crown root stage/)
})
