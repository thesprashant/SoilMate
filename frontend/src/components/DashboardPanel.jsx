import React from 'react'
import {
  Activity,
  ShieldCheck,
  Calendar,
  User,
  History,
  Sparkles
} from 'lucide-react'
import AdvicePanel from './AdvicePanel'
import SchedulePanel from './SchedulePanel'
import ChatProfilePanel from './ChatProfilePanel'
import AgentTraceView from './AgentTraceView'
import LiveProgressTicker from './LiveProgressTicker'
import AdvisoryHistory from './AdvisoryHistory'
import SessionHistory from './SessionHistory'
import CalendarHistory from './CalendarHistory'
import { getUITranslations } from '../utils/translations'

export default function DashboardPanel({
  location,
  uiLanguage = 'hi',
  activeSessionId,
  onSelectSession,
  onNewSession,
  activeTab,
  setActiveTab,
  latestToolCalls,
  streamingEvent,
  latestAdvisory,
  latestCalendar,
  calendarError,
  calendarRevision,
  calendarDraft,
  latestAssistantMessage,
  farmerProfile,
  onSaveProfile,
  onOpenAdvisory,
  onDeleteAdvisory
}) {
  const t = getUITranslations(uiLanguage)

  const TABS = [
    { id: 'advice', label: t.tabAdvice, icon: ShieldCheck },
    { id: 'schedule', label: t.tabSchedule, icon: Calendar },
    { id: 'profile', label: t.tabProfile, icon: User },
    { id: 'history', label: t.tabHistory, icon: History }
  ]
  return (
    <main className="flex-1 min-w-0 flex flex-col lg:h-full lg:overflow-hidden bg-dark-950/70 p-3 sm:p-5 lg:p-6 space-y-4">
      {/* 5 Tabs Floating Rounded Box with Shadows */}
      <div className="rounded-2xl border border-purple-500/25 bg-dark-900/80 p-1.5 shadow-[0_12px_36px_rgba(0,0,0,0.55)] backdrop-blur-xl shrink-0 flex items-center gap-1.5 overflow-x-auto scrollbar-none">
        {TABS.map((tab) => {
          const Icon = tab.icon
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              aria-pressed={isActive}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 min-w-[130px] flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl text-xs font-bold transition whitespace-nowrap ${
                isActive
                  ? 'bg-gradient-to-r from-purple-600 to-indigo-600 text-white shadow-[0_0_24px_rgba(168,85,247,0.45)] border border-purple-400/40'
                  : 'text-purple-300 hover:text-white hover:bg-purple-950/40'
              }`}
            >
              <Icon size={15} className={isActive ? 'text-white' : 'text-purple-400'} />
              <span>{tab.label}</span>
              {tab.id === 'workflow' && streamingEvent && (
                <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping ml-1" />
              )}
            </button>
          )
        })}
      </div>

      {/* Main Tab Content Viewport */}
      <div className="flex-1 overflow-y-auto pr-1 pb-4 scroll-thin rounded-3xl border border-purple-500/15 bg-dark-900/40 p-4 shadow-[0_16px_48px_rgba(0,0,0,0.6)] backdrop-blur-xl">
        {/* 1. AGENT WORKFLOW (Default) */}
        {activeTab === 'workflow' && (
          <div className="space-y-4">
            {/* Live Progress Ticker if active */}
            {streamingEvent && (
              <div className="p-1">
                <LiveProgressTicker event={streamingEvent} />
              </div>
            )}

            {/* Current Turn Tool Execution Trace */}
            {latestToolCalls && latestToolCalls.length > 0 ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between text-xs text-purple-300 font-semibold px-1">
                  <span>{t.traceTitle || 'Autonomous ReAct Tool Execution Trace'}</span>
                  <span className="text-[10px] font-mono text-cyan-300">
                    {latestToolCalls.length} {t.toolsInvoked || 'tool(s) invoked'}
                  </span>
                </div>
                <AgentTraceView toolCalls={latestToolCalls} t={t} />
              </div>
            ) : (
              <div className="rounded-2xl border border-purple-500/20 bg-dark-900/50 p-6 text-center backdrop-blur-md shadow-glass space-y-4">
                <div className="p-3.5 rounded-2xl bg-purple-950/80 border border-purple-500/30 text-purple-400 inline-block">
                  <Activity size={28} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">{t.workflowTitle || 'Agent Workflow Live Monitor'}</h3>
                  <p className="text-xs text-purple-300/70 max-w-md mx-auto mt-1 leading-relaxed">
                    Tool activity appears here when SoilMate retrieves data. Expand a result to inspect its source, timestamps and any missing information.
                  </p>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 max-w-lg mx-auto text-left text-xs pt-2">
                  <div className="p-3 rounded-xl bg-purple-950/30 border border-purple-500/15">
                    <span className="text-[10px] font-bold text-purple-400 uppercase block">{t.workflowStep1Title || '1. Ingestion'}</span>
                    <p className="text-purple-200 mt-0.5">Speech transcription or typed question.</p>
                  </div>
                  <div className="p-3 rounded-xl bg-purple-950/30 border border-purple-500/15">
                    <span className="text-[10px] font-bold text-cyan-400 uppercase block">{t.workflowStep2Title || '2. Dynamic Tools'}</span>
                    <p className="text-purple-200 mt-0.5">Weather, soil estimates, prices and official references, with explicit failure states.</p>
                  </div>
                  <div className="p-3 rounded-xl bg-purple-950/30 border border-purple-500/15">
                    <span className="text-[10px] font-bold text-emerald-400 uppercase block">{t.workflowStep3Title || '3. Localized Output'}</span>
                    <p className="text-purple-200 mt-0.5">Response in your conversation language, with saved evidence.</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 2. CROP ADVICE */}
        {activeTab === 'advice' && (
          <AdvicePanel
            advisory={latestAdvisory}
            latestAssistantMessage={latestAssistantMessage}
            t={t}
          />
        )}

        {/* 3. PLANTING SCHEDULE */}
        {activeTab === 'schedule' && (
          <SchedulePanel
            advisory={calendarDraft ? { crop_name: calendarDraft.crop, evidence: { schedule: calendarDraft.entries } } : latestCalendar}
            error={calendarError}
            sessionId={activeSessionId}
            language={uiLanguage}
            t={t}
          />
        )}

        {/* 4. CHAT PROFILE */}
        {activeTab === 'profile' && (
          <ChatProfilePanel
            location={location}
            language={uiLanguage}
            sessionId={activeSessionId}
            farmerProfile={farmerProfile}
            onSave={onSaveProfile}
            t={t}
          />
        )}

        {/* 5. HISTORY */}
        {activeTab === 'history' && (
          <div className="space-y-5">
            <CalendarHistory language={uiLanguage} t={t} revision={calendarRevision} />
            <AdvisoryHistory sessionId={activeSessionId} t={t} onOpen={onOpenAdvisory} onDelete={onDeleteAdvisory} />
            <SessionHistory
              activeSessionId={activeSessionId}
              onSelectSession={onSelectSession}
              onNewSession={onNewSession}
              t={t}
            />
          </div>
        )}
      </div>
    </main>
  )
}
