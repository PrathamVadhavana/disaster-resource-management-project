'use client'

import React from 'react'
import { AlertTriangle, Clock, ShieldCheck, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/lib/auth-provider'

export function VerificationBanner() {
    const { profile } = useAuth()

    // Admins and victims don't need a verification banner in the same way
    if (!profile || profile.role === 'admin' || profile.role === 'victim') {
        return null
    }

    const status = (profile as any).verification_status || (profile as any).metadata?.verification_status || 'pending'
    if (status === 'verified') return null

    return (
        <div
            className={cn(
                "mb-6 p-4 rounded-2xl border flex items-start gap-4 animate-in fade-in slide-in-from-top-2 duration-500",
                status === 'rejected'
                    ? "bg-red-50 border-red-200 dark:bg-red-500/10 dark:border-red-500/20"
                    : "bg-amber-50 border-amber-200 dark:bg-amber-500/10 dark:border-amber-500/20"
            )}
        >
            <div className={cn(
                "p-2 rounded-xl",
                status === 'rejected' ? "bg-red-100 dark:bg-red-500/20" : "bg-amber-100 dark:bg-amber-500/20"
            )}>
                {status === 'rejected' ? (
                    <XCircle className="w-5 h-5 text-red-600 dark:text-red-400" />
                ) : (
                    <Clock className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                )}
            </div>

            <div className="flex-1">
                <h3 className={cn(
                    "text-sm font-bold",
                    status === 'rejected' ? "text-red-900 dark:text-red-300" : "text-amber-900 dark:text-amber-300"
                )}>
                    {status === 'rejected' ? "Verification Rejected" : "Verification Pending"}
                </h3>
                <p className={cn(
                    "text-xs mt-1 leading-relaxed",
                    status === 'rejected' ? "text-red-700 dark:text-red-400" : "text-amber-700 dark:text-amber-400"
                )}>
                    {status === 'rejected'
                        ? "Your account verification was rejected. Please contact support or check your email for more details. Some features may be restricted."
                        : "Our team is currently reviewing your account. For security, certain features like resource claiming and donation management are restricted until you are verified."
                    }
                </p>

                {status === 'pending' && (
                    <div className="mt-3 flex items-center gap-2">
                        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-amber-100 dark:bg-amber-500/20 text-[10px] font-bold text-amber-700 dark:text-amber-400 uppercase tracking-tighter">
                            <ShieldCheck className="w-3 h-3" /> Usually verified within 24h
                        </span>
                    </div>
                )}
            </div>
        </div>
    )
}
