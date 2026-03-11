'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Mail, Loader2, CheckCircle, ShieldCheck } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';

const forgotPasswordSchema = z.object({
    email: z.string().email('Please enter a valid email address'),
});

type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>;

export default function ForgotPasswordPage() {
    const [isLoading, setIsLoading] = useState(false);
    const [isSubmitted, setIsSubmitted] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const form = useForm<ForgotPasswordValues>({
        resolver: zodResolver(forgotPasswordSchema),
        defaultValues: { email: '' },
    });

    const onSubmit = async (data: ForgotPasswordValues) => {
        setIsLoading(true);
        setError(null);

        try {
            const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            const res = await fetch(`${API_BASE}/api/auth/forgot-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: data.email.trim().toLowerCase() }),
            });

            if (res.status === 429) {
                setError('Too many requests. Please wait a few minutes before trying again.');
                return;
            }

            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                throw new Error(body?.detail || 'Something went wrong. Please try again.');
            }

            setIsSubmitted(true);
        } catch (err: any) {
            setError(err.message || 'Failed to send reset link. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-white dark:bg-slate-950 flex flex-col items-center justify-center p-4 relative overflow-hidden">
            {/* Background */}
            <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none">
                <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-500/10 dark:bg-blue-600/20 rounded-full blur-[120px]" />
                <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-emerald-500/10 dark:bg-emerald-500/10 rounded-full blur-[120px]" />
            </div>

            <div className="w-full max-w-md relative z-10">
                <Link
                    href="/login"
                    className="inline-flex items-center text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white mb-8 transition-colors"
                >
                    <ArrowLeft className="w-4 h-4 mr-2" />
                    Back to Login
                </Link>

                <div className="text-center mb-8">
                    <h1 className="text-4xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-emerald-600 dark:from-blue-400 dark:to-emerald-400 mb-2">
                        Hope in Chaos
                    </h1>
                    <p className="text-slate-600 dark:text-slate-400 font-medium">Disaster Relief Coordination Platform</p>
                </div>

                <div className="w-full max-w-md mx-auto p-8 rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl transition-all">
                    {isSubmitted ? (
                        /* Success State */
                        <div className="text-center space-y-4">
                            <div className="w-16 h-16 bg-emerald-100 dark:bg-emerald-900/30 rounded-full flex items-center justify-center mx-auto">
                                <CheckCircle className="w-8 h-8 text-emerald-600 dark:text-emerald-400" />
                            </div>
                            <h2 className="text-2xl font-bold text-slate-900 dark:text-white">
                                Check Your Email
                            </h2>
                            <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
                                If an account exists with the email you provided, we&apos;ve sent a password reset link.
                                Please check your inbox and spam folder.
                            </p>
                            <p className="text-xs text-slate-400 dark:text-slate-500">
                                The link will expire in 1 hour for security purposes.
                            </p>
                            <div className="pt-4 space-y-3">
                                <Link
                                    href="/login"
                                    className="block w-full bg-blue-600 hover:bg-blue-700 text-white font-bold h-11 rounded-xl flex items-center justify-center gap-2 transition-all shadow-lg shadow-blue-600/20"
                                >
                                    Return to Login
                                </Link>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setIsSubmitted(false);
                                        form.reset();
                                    }}
                                    className="w-full text-sm text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 font-medium"
                                >
                                    Try a different email
                                </button>
                            </div>
                        </div>
                    ) : (
                        /* Form State */
                        <>
                            <div className="text-center mb-8">
                                <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">
                                    Forgot Password?
                                </h2>
                                <p className="text-sm text-slate-500 dark:text-slate-400">
                                    Enter your registered email address and we&apos;ll send you a link to reset your password.
                                </p>
                            </div>

                            {error && (
                                <div className="mb-6 p-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/30 flex items-start gap-3">
                                    <ShieldCheck className="w-5 h-5 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
                                    <p className="text-sm text-red-600 dark:text-red-400 font-medium">{error}</p>
                                </div>
                            )}

                            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
                                <div className="space-y-2">
                                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                                        Email Address
                                    </label>
                                    <div className="relative">
                                        <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400" />
                                        <input
                                            {...form.register('email')}
                                            type="email"
                                            autoComplete="email"
                                            className="pl-10 flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm placeholder:text-slate-500 focus-visible:outline-none focus:ring-2 focus:ring-blue-600 transition-all dark:border-slate-800 dark:bg-slate-950 dark:placeholder:text-slate-400 dark:focus:ring-blue-500"
                                            placeholder="you@example.com"
                                        />
                                    </div>
                                    {form.formState.errors.email && (
                                        <p className="text-xs text-red-500 font-medium">
                                            {form.formState.errors.email.message}
                                        </p>
                                    )}
                                </div>

                                <button
                                    type="submit"
                                    disabled={isLoading}
                                    className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold h-11 rounded-xl flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-blue-600/20"
                                >
                                    {isLoading ? (
                                        <Loader2 className="h-5 w-5 animate-spin" />
                                    ) : (
                                        <>
                                            Send Reset Link
                                            <Mail className="h-5 w-5" />
                                        </>
                                    )}
                                </button>

                                <div className="pt-4 text-center text-sm">
                                    <span className="text-slate-500 dark:text-slate-400">Remember your password? </span>
                                    <Link
                                        href="/login"
                                        className="text-blue-600 font-bold hover:underline"
                                    >
                                        Log in
                                    </Link>
                                </div>
                            </form>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
