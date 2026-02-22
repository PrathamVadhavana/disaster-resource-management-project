'use client'

import { useState } from 'react'
import dynamic from 'next/dynamic'
import {
  FileText, MessageSquare, AlertTriangle, Target,
  LayoutDashboard, ChevronRight
} from 'lucide-react'

const SituationReportPanel = dynamic(
  () => import('@/components/coordinator/SituationReportPanel'),
  { loading: () => <PanelSkeleton /> }
)
const NLQueryWidget = dynamic(
  () => import('@/components/coordinator/NLQueryWidget'),
  { loading: () => <PanelSkeleton /> }
)
const AnomalyAlertPanel = dynamic(
  () => import('@/components/coordinator/AnomalyAlertPanel'),
  { loading: () => <PanelSkeleton /> }
)
const OutcomeTrackingPanel = dynamic(
  () => import('@/components/coordinator/OutcomeTrackingPanel'),
  { loading: () => <PanelSkeleton /> }
)

function PanelSkeleton() {
  return <div className="animate-pulse h-64 rounded-2xl bg-slate-100 dark:bg-slate-800" />
}

type Tab = 'overview' | 'sitrep' | 'query' | 'anomalies' | 'outcomes'

const TABS: { id: Tab; label: string; icon: typeof FileText; description: string }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, description: 'Dashboard summary' },
  { id: 'sitrep', label: 'Situation Reports', icon: FileText, description: 'AI-generated briefings' },
  { id: 'query', label: 'Data Query', icon: MessageSquare, description: 'Chat with your data' },
  { id: 'anomalies', label: 'Anomalies', icon: AlertTriangle, description: 'ML-detected alerts' },
  { id: 'outcomes', label: 'Outcomes', icon: Target, description: 'Model feedback loop' },
]

export default function CoordinatorDashboardPage() {
  const [activeTab, setActiveTab] = useState<Tab>('overview')

  return (
    <div className="space-y-6 p-4 md:p-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          AI Coordinator Dashboard
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          AI-powered decision support: situation reports, anomaly alerts, natural language queries, and outcome tracking
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 p-1 rounded-xl bg-slate-100 dark:bg-white/5 overflow-x-auto">
        {TABS.map(tab => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
                activeTab === tab.id
                  ? 'bg-white dark:bg-white/10 text-slate-900 dark:text-white shadow-sm'
                  : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Quick action cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {TABS.filter(t => t.id !== 'overview').map(tab => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 text-left hover:border-blue-300 dark:hover:border-blue-500/30 transition-colors group"
                >
                  <Icon className="w-6 h-6 text-blue-500 mb-3" />
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                    {tab.label}
                  </h3>
                  <p className="text-xs text-slate-500 mt-1">{tab.description}</p>
                  <div className="flex items-center gap-1 text-xs text-blue-500 mt-3 group-hover:translate-x-1 transition-transform">
                    Open <ChevronRight className="w-3 h-3" />
                  </div>
                </button>
              )
            })}
          </div>

          {/* Overview panels - show latest sitrep + anomalies + NL query side by side */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div>
              <SituationReportPanel />
            </div>
            <div className="space-y-6">
              <AnomalyAlertPanel />
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <NLQueryWidget />
            <OutcomeTrackingPanel />
          </div>
        </div>
      )}

      {activeTab === 'sitrep' && <SituationReportPanel />}
      {activeTab === 'query' && (
        <div className="max-w-3xl mx-auto">
          <NLQueryWidget />
        </div>
      )}
      {activeTab === 'anomalies' && <AnomalyAlertPanel />}
      {activeTab === 'outcomes' && <OutcomeTrackingPanel />}
    </div>
  )
}
