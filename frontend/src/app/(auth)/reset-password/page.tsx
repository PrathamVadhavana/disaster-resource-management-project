'use client';

import { useState, useEffect, useRef, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Loader2, CheckCircle, ShieldCheck, Lock, XCircle } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { getSupabaseClient } from '@/lib/supabase/client';
import { PasswordInput } from '@/components/ui/PasswordInput';

const resetPasswordSchema = z
    .object({
        password: z
            .string()
            .min(8, 'Password must be at least 8 characters')
            .regex(/[A-Z]/, 'Password must contain at least one uppercase letter')
            .regex(/[0-9]/, 'Password must contain at least one number')
            .regex(/[^A-Za-z0-9]/, 'Password must contain at least one special character'),
        confirmPassword: z.string().min(1, 'Please confirm your password'),
    })
    .refine((data) => data.password === data.confirmPassword, {
        message: 'Passwords do not match',
        path: ['confirmPassword'],
    });

type ResetPasswordValues = z.infer<typeof resetPasswordSchema>;

type PageState = 'loading' | 'ready' | 'submitting' | 'success' | 'error';

export default function ResetPasswordPage() {
    return (
        <Suspense
            fallback={
                <div className="min-h-screen bg-white dark:bg-slate-950 flex items-center justify-center">
                    <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
                </div>
            }
        >
            <ResetPasswordContent />
        </Suspense>
    );
}

function ResetPasswordContent() {
    const [pageState, setPageState] = useState<PageState>('loading');
    const [error, setError] = useState<string | null>(null);
    const [accessToken, setAccessToken] = useState<string | null>(null);
    const router = useRouter();
    const searchParams = useSearchParams();
    const initialized = useRef(false);

    const form = useForm<ResetPasswordValues>({
        resolver: zodResolver(resetPasswordSchema),
        defaultValues: { password: '', confirmPassword: '' },
    });

    // Handle the Supabase recovery redirect
    useEffect(() => {
        if (initialized.current) return;
        initialized.current = true;

        const processRecovery = async () => {
            const supabase = getSupabaseClient();

            // Check for PKCE code in URL query params (Supabase v2+ flow)
            const code = searchParams.get('code');
            if (code) {
                try {
                    const { data, error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
                    if (exchangeError) throw exchangeError;
                    if (data.session?.access_token) {
                        setAccessToken(data.session.access_token);
                        setPageState('ready');
                        return;
                    }
                } catch (err: any) {
                    console.error('Code exchange error:', err);
                    setError('This reset link is invalid or has expired. Please request a new one.');
                    setPageState('error');
                    return;
                }
            }

            // Check for hash fragment tokens (older Supabase flow)
            if (typeof window !== 'undefined' && window.location.hash) {
                const hashParams = new URLSearchParams(window.location.hash.substring(1));
                const tokenFromHash = hashParams.get('access_token');
                const type = hashParams.get('type');

                if (tokenFromHash && type === 'recovery') {
                    try {
                        const { data, error: sessionError } = await supabase.auth.setSession({
                            access_token: tokenFromHash,
                            refresh_token: hashParams.get('refresh_token') || '',
                        });
                        if (sessionError) throw sessionError;
                        setAccessToken(data.session?.access_token || tokenFromHash);
                        setPageState('ready');
                        return;
                    } catch (err: any) {
                        console.error('Session set error:', err);
                        setError('This reset link is invalid or has expired. Please request a new one.');
                        setPageState('error');
                        return;
                    }
                }
            }

            // Listen for PASSWORD_RECOVERY event (Supabase may auto-detect the hash)
            const { data: { subscription } } = supabase.auth.onAuthStateChange(
                async (event, session) => {
                    if (event === 'PASSWORD_RECOVERY' && session?.access_token) {
                        setAccessToken(session.access_token);
                        setPageState('ready');
                        subscription.unsubscribe();
                    }
                },
            );

            // Wait briefly for Supabase to process the URL
            await new Promise((r) => setTimeout(r, 2000));

            // If still loading, check if there's an active session
            const { data: { session } } = await supabase.auth.getSession();
            if (session?.access_token) {
                setAccessToken(session.access_token);
                setPageState('ready');
                subscription.unsubscribe();
                return;
            }

            // No valid recovery token found
            setError('No valid reset token found. Please request a new password reset link.');
            setPageState('error');
            subscription.unsubscribe();
        };

        processRecovery();
    }, [searchParams]);

    const onSubmit = async (data: ResetPasswordValues) => {
        if (!accessToken) {
            setError('Reset session expired. Please request a new link.');
            setPageState('error');
            return;
        }

        setPageState('submitting');
        setError(null);

        try {
            const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            const res = await fetch(`${API_BASE}/api/auth/reset-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    access_token: accessToken,
                    new_password: data.password,
                }),
            });

            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                throw new Error(body?.detail || 'Failed to reset password. Please try again.');
            }

            // Sign out to clear recovery session — user will log in with new password
            const supabase = getSupabaseClient();
            await supabase.auth.signOut();

            // Clear auth cookies
            document.cookie = 'sb-token=; path=/; max-age=0';
            document.cookie = 'sb-role=; path=/; max-age=0';
            document.cookie = 'profile-completed=; path=/; max-age=0';

            setPageState('success');
        } catch (err: any) {
            setError(err.message || 'Failed to reset password.');
            setPageState('ready');
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
                    {pageState === 'loading' && (
                        <div className="text-center space-y-4 py-8">
                            <Loader2 className="w-8 h-8 animate-spin text-blue-600 mx-auto" />
                            <p className="text-sm text-slate-500 dark:text-slate-400">
                                Verifying your reset link...
                            </p>
                        </div>
                    )}

                    {pageState === 'error' && (
                        <div className="text-center space-y-4">
                            <div className="w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center mx-auto">
                                <XCircle className="w-8 h-8 text-red-600 dark:text-red-400" />
                            </div>
                            <h2 className="text-2xl font-bold text-slate-900 dark:text-white">
                                Link Expired or Invalid
                            </h2>
                            <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
                                {error || 'This password reset link has expired or is invalid.'}
                            </p>
                            <div className="pt-4 space-y-3">
                                <Link
                                    href="/forgot-password"
                                    className="block w-full bg-blue-600 hover:bg-blue-700 text-white font-bold h-11 rounded-xl flex items-center justify-center gap-2 transition-all shadow-lg shadow-blue-600/20"
                                >
                                    Request New Reset Link
                                </Link>
                                <Link
                                    href="/login"
                                    className="block w-full text-sm text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 font-medium text-center"
                                >
                                    Return to Login
                                </Link>
                            </div>
                        </div>
                    )}

                    {pageState === 'success' && (
                        <div className="text-center space-y-4">
                            <div className="w-16 h-16 bg-emerald-100 dark:bg-emerald-900/30 rounded-full flex items-center justify-center mx-auto">
                                <CheckCircle className="w-8 h-8 text-emerald-600 dark:text-emerald-400" />
                            </div>
                            <h2 className="text-2xl font-bold text-slate-900 dark:text-white">
                                Password Reset Successfully
                            </h2>
                            <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
                                Your password has been updated. You can now log in with your new password.
                            </p>
                            <div className="pt-4">
                                <button
                                    onClick={() => router.push('/login')}
                                    className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold h-11 rounded-xl flex items-center justify-center gap-2 transition-all shadow-lg shadow-blue-600/20"
                                >
                                    Go to Login
                                </button>
                            </div>
                        </div>
                    )}

                    {(pageState === 'ready' || pageState === 'submitting') && (
                        <>
                            <div className="text-center mb-8">
                                <div className="w-16 h-16 bg-blue-100 dark:bg-blue-900/30 rounded-full flex items-center justify-center mx-auto mb-4">
                                    <Lock className="w-8 h-8 text-blue-600 dark:text-blue-400" />
                                </div>
                                <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">
                                    Set New Password
                                </h2>
                                <p className="text-sm text-slate-500 dark:text-slate-400">
                                    Choose a strong password for your account.
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
                                        New Password
                                    </label>
                                    <PasswordInput
                                        {...form.register('password')}
                                        placeholder="Min 8 chars, 1 upper, 1 number, 1 special"
                                        autoComplete="new-password"
                                    />
                                    {form.formState.errors.password && (
                                        <p className="text-xs text-red-500 font-medium">
                                            {form.formState.errors.password.message}
                                        </p>
                                    )}
                                </div>

                                <div className="space-y-2">
                                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                                        Confirm New Password
                                    </label>
                                    <PasswordInput
                                        {...form.register('confirmPassword')}
                                        placeholder="Re-enter your new password"
                                        autoComplete="new-password"
                                    />
                                    {form.formState.errors.confirmPassword && (
                                        <p className="text-xs text-red-500 font-medium">
                                            {form.formState.errors.confirmPassword.message}
                                        </p>
                                    )}
                                </div>

                                {/* Password Requirements */}
                                <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700">
                                    <p className="text-xs font-medium text-slate-600 dark:text-slate-300 mb-2">Password Requirements:</p>
                                    <ul className="text-xs text-slate-500 dark:text-slate-400 space-y-1">
                                        <li className="flex items-center gap-2">
                                            <span className={form.watch('password')?.length >= 8 ? 'text-emerald-500' : ''}>
                                                {form.watch('password')?.length >= 8 ? '✓' : '○'}
                                            </span>
                                            At least 8 characters
                                        </li>
                                        <li className="flex items-center gap-2">
                                            <span className={/[A-Z]/.test(form.watch('password') || '') ? 'text-emerald-500' : ''}>
                                                {/[A-Z]/.test(form.watch('password') || '') ? '✓' : '○'}
                                            </span>
                                            One uppercase letter
                                        </li>
                                        <li className="flex items-center gap-2">
                                            <span className={/[0-9]/.test(form.watch('password') || '') ? 'text-emerald-500' : ''}>
                                                {/[0-9]/.test(form.watch('password') || '') ? '✓' : '○'}
                                            </span>
                                            One number
                                        </li>
                                        <li className="flex items-center gap-2">
                                            <span className={/[^A-Za-z0-9]/.test(form.watch('password') || '') ? 'text-emerald-500' : ''}>
                                                {/[^A-Za-z0-9]/.test(form.watch('password') || '') ? '✓' : '○'}
                                            </span>
                                            One special character
                                        </li>
                                    </ul>
                                </div>

                                <button
                                    type="submit"
                                    disabled={pageState === 'submitting'}
                                    className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold h-11 rounded-xl flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-blue-600/20"
                                >
                                    {pageState === 'submitting' ? (
                                        <Loader2 className="h-5 w-5 animate-spin" />
                                    ) : (
                                        <>
                                            Reset Password
                                            <Lock className="h-5 w-5" />
                                        </>
                                    )}
                                </button>
                            </form>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
