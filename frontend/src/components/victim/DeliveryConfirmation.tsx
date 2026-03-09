'use client'

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { confirmDelivery } from '@/lib/api/workflow'
import { CheckCircle2, Star, Camera, Loader2, AlertCircle } from 'lucide-react'

interface DeliveryConfirmationProps {
    requestId: string
    onConfirmed?: () => void
}

export function DeliveryConfirmation({ requestId, onConfirmed }: DeliveryConfirmationProps) {
    const queryClient = useQueryClient()
    const [code, setCode] = useState('')
    const [rating, setRating] = useState(0)
    const [feedback, setFeedback] = useState('')
    const [hoverRating, setHoverRating] = useState(0)
    const [error, setError] = useState<string | null>(null)

    const mutation = useMutation({
        mutationFn: () => confirmDelivery(requestId, {
            confirmation_code: code,
            rating: rating || undefined,
            feedback: feedback || undefined,
        }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['victim-request', requestId] })
            queryClient.invalidateQueries({ queryKey: ['victim-requests'] })
            queryClient.invalidateQueries({ queryKey: ['victim-stats'] })
            onConfirmed?.()
        },
        onError: (err: Error) => {
            setError(err.message)
        },
    })

    return (
        <div className="rounded-xl border border-green-200 bg-green-50/50 dark:bg-green-950/20 dark:border-green-800 p-6 space-y-4">
            <div className="flex items-center gap-2 text-green-700 dark:text-green-400">
                <CheckCircle2 className="w-5 h-5" />
                <h3 className="font-semibold text-lg">Confirm Delivery</h3>
            </div>

            <p className="text-sm text-slate-600 dark:text-slate-400">
                Your resources have been delivered. Enter the confirmation code provided by the delivery
                team to verify receipt.
            </p>

            {error && (
                <div className="flex items-center gap-2 text-red-600 bg-red-50 dark:bg-red-950/30 rounded-lg p-3 text-sm">
                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                    {error}
                </div>
            )}

            {/* Confirmation Code */}
            <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Confirmation Code *
                </label>
                <input
                    type="text"
                    value={code}
                    onChange={(e) => { setCode(e.target.value.toUpperCase()); setError(null) }}
                    placeholder="Enter code (e.g. A3X7K2)"
                    maxLength={10}
                    className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:ring-2 focus:ring-green-500 focus:border-transparent"
                />
            </div>

            {/* Star Rating */}
            <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Rate the delivery (optional)
                </label>
                <div className="flex gap-1">
                    {[1, 2, 3, 4, 5].map((star) => (
                        <button
                            key={star}
                            type="button"
                            onClick={() => setRating(star)}
                            onMouseEnter={() => setHoverRating(star)}
                            onMouseLeave={() => setHoverRating(0)}
                            className="p-1 transition-transform hover:scale-110"
                        >
                            <Star
                                className={`w-6 h-6 transition-colors ${
                                    star <= (hoverRating || rating)
                                        ? 'text-yellow-400 fill-yellow-400'
                                        : 'text-slate-300 dark:text-slate-600'
                                }`}
                            />
                        </button>
                    ))}
                    {rating > 0 && (
                        <span className="ml-2 text-sm text-slate-500 self-center">
                            {rating}/5
                        </span>
                    )}
                </div>
            </div>

            {/* Feedback */}
            <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Feedback (optional)
                </label>
                <textarea
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    placeholder="How was the delivery experience?"
                    rows={2}
                    maxLength={1000}
                    className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:ring-2 focus:ring-green-500 focus:border-transparent resize-none"
                />
            </div>

            {/* Submit */}
            <button
                onClick={() => mutation.mutate()}
                disabled={!code || code.length < 4 || mutation.isPending}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-green-600 hover:bg-green-700 text-white font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
                {mutation.isPending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                    <CheckCircle2 className="w-4 h-4" />
                )}
                {mutation.isPending ? 'Confirming...' : 'Confirm Delivery'}
            </button>

            {mutation.isSuccess && (
                <div className="text-center text-green-600 dark:text-green-400 font-medium text-sm">
                    Delivery confirmed successfully! Thank you for your feedback.
                </div>
            )}
        </div>
    )
}
