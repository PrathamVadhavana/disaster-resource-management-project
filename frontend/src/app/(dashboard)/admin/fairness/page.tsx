'use client'

import { Suspense } from 'react'
import { FairnessSlider } from '@/components/admin/FairnessSlider'
import { useSearchParams } from 'next/navigation'
import { Scale, Loader2 } from 'lucide-react'

function FairnessContent() {
    const params = useSearchParams()
    const disasterId = params.get('disaster_id') ?? undefined

    return (
        <div className="space-y-6">
            <div>
                <div className="flex items-center gap-3 mb-1">
                    <div className="p-2 rounded-xl bg-indigo-100 dark:bg-indigo-950/30">
                        <Scale className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                    </div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Fairness-Constrained Allocation</h1>
                </div>
                <p className="text-sm text-slate-500 dark:text-slate-400 ml-12">
                    Explore the Pareto frontier between allocation efficiency and equity. Adjust the slider to preview trade-offs, then apply your chosen plan.
                </p>
            </div>

            <FairnessSlider disasterId={disasterId} />
        </div>
    )
}

export default function FairnessPage() {
    return (
        <Suspense fallback={<div className="flex items-center justify-center h-64"><Loader2 className="w-8 h-8 animate-spin text-indigo-500" /></div>}>
            <FairnessContent />
        </Suspense>
    )
}
