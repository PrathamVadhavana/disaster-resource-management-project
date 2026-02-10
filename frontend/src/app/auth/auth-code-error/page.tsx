'use client';

import { useSearchParams } from 'next/navigation';
import { Suspense } from 'react';
import Link from 'next/link';
import { AlertTriangle, ArrowLeft, RefreshCw } from 'lucide-react';

function AuthErrorContent() {
    const searchParams = useSearchParams();
    const error = searchParams.get('error') || 'unknown_error';
    const errorDescription = searchParams.get('error_description') || 'An unexpected error occurred during authentication.';
    const errorCode = searchParams.get('error_code') || '';

    const getErrorMessage = () => {
        switch (error) {
            case 'server_error':
                if (errorDescription.includes('saving new user')) {
                    return 'There was a database issue while creating your account. This is usually temporary — please try again.';
                }
                return 'A server error occurred. Please try again later.';
            case 'access_denied':
                return 'Access was denied. You may have cancelled the login process.';
            case 'invalid_request':
                return 'The authentication request was invalid. Please try signing in again.';
            default:
                return errorDescription;
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 p-4">
            <div className="w-full max-w-md p-8 rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl">
                <div className="text-center mb-6">
                    <div className="mx-auto w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/20 flex items-center justify-center mb-4">
                        <AlertTriangle className="w-8 h-8 text-red-600 dark:text-red-400" />
                    </div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">
                        Authentication Error
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400">
                        {getErrorMessage()}
                    </p>
                </div>

                {errorCode && (
                    <div className="mb-6 p-3 rounded-lg bg-slate-100 dark:bg-slate-800 text-xs text-slate-500 dark:text-slate-400 font-mono text-center">
                        Error code: {errorCode}
                    </div>
                )}

                <div className="space-y-3">
                    <Link
                        href="/login"
                        className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold h-11 rounded-xl flex items-center justify-center gap-2 transition-all shadow-lg shadow-blue-600/20"
                    >
                        <RefreshCw className="h-4 w-4" /> Try Again
                    </Link>
                    <Link
                        href="/"
                        className="w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 font-bold h-11 rounded-xl flex items-center justify-center gap-2 hover:bg-slate-50 dark:hover:bg-slate-750 transition-all"
                    >
                        <ArrowLeft className="h-4 w-4" /> Back to Home
                    </Link>
                </div>
            </div>
        </div>
    );
}

export default function AuthCodeErrorPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950">
                <div className="animate-pulse text-slate-500">Loading...</div>
            </div>
        }>
            <AuthErrorContent />
        </Suspense>
    );
}
