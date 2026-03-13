import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Loader2, Package, User, MapPin, Calendar, AlertTriangle } from 'lucide-react'

interface ResourceDetailModalProps {
  isOpen: boolean
  onClose: () => void
  resource: any
}

export function ResourceDetailModal({ isOpen, onClose, resource }: ResourceDetailModalProps) {
  if (!isOpen || !resource) return null

  const remaining = Math.max(0, (resource.total_quantity || 0) - (resource.claimed_quantity || 0))
  const total = resource.total_quantity || 0
  const pct = total > 0 ? Math.round((remaining / total) * 100) : 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center">
              <Package className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">{resource.title}</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400 capitalize">{resource.category} · {resource.resource_type}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors"
          >
            <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Status Badge */}
        <div className="mb-4 flex items-center gap-2">
          <span className={cn(
            'text-xs font-bold px-2 py-0.5 rounded-full',
            resource.status === 'available'
              ? 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400'
              : 'bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400'
          )}>
            {resource.status}
          </span>
          {pct < 20 && (
            <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              Low Stock
            </span>
          )}
        </div>

        {/* Quantity Info */}
        <div className="mb-4 p-3 bg-slate-50 dark:bg-white/[0.03] rounded-xl">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-slate-500 dark:text-slate-400">Quantity</span>
            <span className="text-sm font-semibold text-slate-900 dark:text-white">
              {remaining} of {total} {resource.unit}
            </span>
          </div>
          <div className="h-2 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
            <div
              className={cn(
                'h-full rounded-full transition-all',
                pct > 50 ? 'bg-emerald-500' : pct > 20 ? 'bg-amber-500' : 'bg-red-500'
              )}
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{pct}% remaining</p>
        </div>

        {/* Provider Info */}
        <div className="mb-4 p-3 bg-slate-50 dark:bg-white/[0.03] rounded-xl">
          <div className="flex items-center gap-2 mb-2">
            <User className="w-4 h-4 text-slate-500" />
            <span className="text-sm font-medium text-slate-900 dark:text-white">Provider</span>
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-300">{resource.provider_name || 'Unknown'}</p>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 capitalize">{resource.provider_role || 'unknown'}</p>
        </div>

        {/* Location Info */}
        <div className="mb-4 p-3 bg-slate-50 dark:bg-white/[0.03] rounded-xl">
          <div className="flex items-center gap-2 mb-2">
            <MapPin className="w-4 h-4 text-slate-500" />
            <span className="text-sm font-medium text-slate-900 dark:text-white">Location</span>
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-300">{resource.address_text || '—'}</p>
        </div>

        {/* Description */}
        {resource.description && (
          <div className="mb-4 p-3 bg-slate-50 dark:bg-white/[0.03] rounded-xl">
            <div className="flex items-center gap-2 mb-2">
              <Calendar className="w-4 h-4 text-slate-500" />
              <span className="text-sm font-medium text-slate-900 dark:text-white">Description</span>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-300">{resource.description}</p>
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <Button onClick={onClose} className="flex-1">
            Close
          </Button>
        </div>
      </div>
    </div>
  )
}

// Helper function for conditional class names
function cn(...classes: string[]) {
  return classes.filter(Boolean).join(' ')
}