'use client';

import { useState, useEffect, useRef, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Loader2, CheckCircle, ShieldCheck, Lock, XCircle, Eye, EyeOff } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { getSupabaseClient } from '@/lib/supabase/client';

const schema = z.object({
    password: z.string()
        .min(8, 'At least 8 characters')
        .regex(/[A-Z]/, 'One uppercase letter required')
        .regex(/[0-9]/, 'One number required')
        .regex(/[^A-Za-z0-9]/, 'One special character required'),
    confirmPassword: z.string(),
}).refine(d => d.password === d.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
});

type FormValues = z.infer<typeof schema>;
type State = 'loading' | 'ready' | 'submitting' | 'success' | 'error';

export default function ResetPasswordPage() {
    return (
        <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-blue-600" /></div>}>
            <Content />
        </Suspense>
    );
}

function StrengthBar({ pw }: { pw: string }) {
    const checks = [pw.length >= 8, /[A-Z]/.test(pw), /[0-9]/.test(pw), /[^A-Za-z0-9]/.test(pw)];
    const score = checks.filter(Boolean).length;
    const colors = ['', 'bg-red-500', 'bg-orange-500', 'bg-yellow-500', 'bg-emerald-500'];
    const labels = ['', 'Weak', 'Fair', 'Good', 'Strong'];
    const textColors = ['', 'text-red-500', 'text-orange-500', 'text-yellow-600', 'text-emerald-500'];
    if (!pw) return null;
    return (
        <div className="space-y-2 pt-1">
            <div className="flex gap-1">
                {[1,2,3,4].map(i => (
                    <div key={i} className={`h-1.5 flex-1 rounded-full transition-all ${i <= score ? colors[score] : 'bg-slate-200 dark:bg-slate-700'}`} />
                ))}
            </div>
            <p className={`text-xs font-semibold ${textColors[score]}`}>{labels[score]}</p>
        </div>
    );
}

function PwField({ label, reg, error, placeholder }: { label: string; reg: any; error?: string; placeholder?: string }) {
    const [show, setShow] = useState(false);
    return (
        <div className="space-y-2">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">{label}</label>
            <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input
                    {...reg}
                    type={show ? 'text' : 'password'}
                    autoComplete="new-password"
                    placeholder={placeholder}
                    className="pl-9 pr-10 h-11 w-full rounded-xl border border-slate-200 bg-white text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-600 transition-all dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                />
                <button type="button" onClick={() => setShow(s => !s)} tabIndex={-1} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors">
                    {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
            </div>
            {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
    );
}

function Content() {
    const [state, setState] = useState<State>('loading');
    const [errorMsg, setErrorMsg] = useState<string | null>(null);
    const router = useRouter();
    const searchParams = useSearchParams();
    const done = useRef(false);

    const form = useForm<FormValues>({
        resolver: zodResolver(schema),
        defaultValues: { password: '', confirmPassword: '' },
    });
    const pw = form.watch('password') || '';

    useEffect(() => {
        if (done.current) return;
        done.current = true;

        const init = async () => {
            const supabase = getSupabaseClient();

            // ── Priority 1: Check for error in hash (e.g. otp_expired, access_denied) ──
            // This MUST be checked first before anything else
            const hash = typeof window !== 'undefined' ? window.location.hash : '';
            if (hash) {
                const hp = new URLSearchParams(hash.replace(/^#/, ''));
                const hashError = hp.get('error');
                const hashErrorCode = hp.get('error_code');
                const hashErrorDesc = hp.get('error_description');

                if (hashError) {
                    let msg = 'This reset link has expired or is invalid.';
                    if (hashErrorCode === 'otp_expired') {
                        msg = 'This reset link has expired. Links are valid for 1 hour and can only be used once. Please request a new one.';
                    } else if (hashErrorDesc) {
                        msg = decodeURIComponent(hashErrorDesc.replace(/\+/g, ' '));
                    }
                    setErrorMsg(msg);
                    setState('error');
                    return;
                }
            }

            // ── Priority 2: PKCE flow — ?code= in query params ──
            const code = searchParams.get('code');
            if (code) {
                try {
                    const { error: ex } = await supabase.auth.exchangeCodeForSession(code);
                    if (ex) throw ex;
                    setState('ready');
                    return;
                } catch (e: any) {
                    setErrorMsg('This reset link is invalid or has already been used. Please request a new one.');
                    setState('error');
                    return;
                }
            }

            // ── Priority 3: Hash fragment with access_token ──
            if (hash) {
                const hp = new URLSearchParams(hash.replace(/^#/, ''));
                const token = hp.get('access_token');
                const type = hp.get('type');
                if (token && type === 'recovery') {
                    try {
                        const { error: se } = await supabase.auth.setSession({
                            access_token: token,
                            refresh_token: hp.get('refresh_token') || '',
                        });
                        if (se) throw se;
                        setState('ready');
                        return;
                    } catch (e: any) {
                        setErrorMsg('This reset link has expired. Please request a new one.');
                        setState('error');
                        return;
                    }
                }
            }

            // ── Priority 4: Listen for PASSWORD_RECOVERY auth event ──
            let resolved = false;
            const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
                if (event === 'PASSWORD_RECOVERY' && session) {
                    resolved = true;
                    setState('ready');
                    subscription.unsubscribe();
                }
            });

            await new Promise(r => setTimeout(r, 2500));

            if (!resolved) {
                const { data: { session } } = await supabase.auth.getSession();
                if (session) {
                    setState('ready');
                } else {
                    setErrorMsg('No valid reset token found. Please request a new password reset link.');
                    setState('error');
                }
                subscription.unsubscribe();
            }
        };

        init();
    }, [searchParams]);

    const onSubmit = async (data: FormValues) => {
        setState('submitting');
        setErrorMsg(null);
        try {
            const supabase = getSupabaseClient();
            const { error: ue } = await supabase.auth.updateUser({ password: data.password });
            if (ue) throw ue;

            await supabase.auth.signOut();
            ['sb-token','sb-role','profile-completed'].forEach(n => {
                document.cookie = `${n}=; path=/; max-age=0; SameSite=Lax`;
            });
            setState('success');
        } catch (e: any) {
            const msg = e.message || 'Failed to update password.';
            if (msg.toLowerCase().includes('session') || msg.toLowerCase().includes('expired')) {
                setErrorMsg('Your reset session has expired. Please request a new link.');
                setState('error');
            } else {
                setErrorMsg(msg);
                setState('ready');
            }
        }
    };

    const bg = (
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
            <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-500/10 dark:bg-blue-600/20 rounded-full blur-[120px]" />
            <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-emerald-500/10 rounded-full blur-[120px]" />
        </div>
    );

    return (
        <div className="min-h-screen bg-white dark:bg-slate-950 flex flex-col items-center justify-center p-4 relative overflow-hidden">
            {bg}
            <div className="w-full max-w-md relative z-10">
                <Link href="/login" className="inline-flex items-center text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white mb-8 transition-colors">
                    <ArrowLeft className="w-4 h-4 mr-2" />Back to Login
                </Link>

                <div className="text-center mb-8">
                    <h1 className="text-4xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-emerald-600 dark:from-blue-400 dark:to-emerald-400 mb-2">Hope in Chaos</h1>
                    <p className="text-slate-600 dark:text-slate-400 font-medium">Disaster Relief Coordination Platform</p>
                </div>

                <div className="w-full mx-auto p-8 rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl">

                    {state === 'loading' && (
                        <div className="text-center py-10 space-y-3">
                            <Loader2 className="w-10 h-10 animate-spin text-blue-600 mx-auto" />
                            <p className="text-sm text-slate-500">Verifying your reset link…</p>
                        </div>
                    )}

                    {state === 'error' && (
                        <div className="text-center space-y-4">
                            <div className="w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center mx-auto">
                                <XCircle className="w-8 h-8 text-red-600 dark:text-red-400" />
                            </div>
                            <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Link Expired or Invalid</h2>
                            <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
                                {errorMsg || 'This password reset link has expired or is invalid.'}
                            </p>
                            <p className="text-xs text-slate-400">Reset links are valid for 1 hour and can only be used once.</p>
                            <div className="pt-4 space-y-3">
                                <Link href="/forgot-password" className="block w-full bg-blue-600 hover:bg-blue-700 text-white font-bold h-11 rounded-xl flex items-center justify-center transition-all shadow-lg shadow-blue-600/20">
                                    Request New Reset Link
                                </Link>
                                <Link href="/login" className="block text-sm text-center text-slate-500 hover:text-slate-700 dark:text-slate-400 font-medium">
                                    Return to Login
                                </Link>
                            </div>
                        </div>
                    )}

                    {state === 'success' && (
                        <div className="text-center space-y-4">
                            <div className="w-16 h-16 bg-emerald-100 dark:bg-emerald-900/30 rounded-full flex items-center justify-center mx-auto">
                                <CheckCircle className="w-8 h-8 text-emerald-600 dark:text-emerald-400" />
                            </div>
                            <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Password Updated!</h2>
                            <p className="text-sm text-slate-500 dark:text-slate-400">You can now log in with your new password.</p>
                            <button onClick={() => router.push('/login')} className="w-full mt-4 bg-blue-600 hover:bg-blue-700 text-white font-bold h-11 rounded-xl flex items-center justify-center transition-all shadow-lg shadow-blue-600/20">
                                Go to Login
                            </button>
                        </div>
                    )}

                    {(state === 'ready' || state === 'submitting') && (
                        <>
                            <div className="text-center mb-6">
                                <div className="w-14 h-14 bg-blue-100 dark:bg-blue-900/30 rounded-full flex items-center justify-center mx-auto mb-4">
                                    <Lock className="w-7 h-7 text-blue-600 dark:text-blue-400" />
                                </div>
                                <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-1">Set New Password</h2>
                                <p className="text-sm text-slate-500 dark:text-slate-400">Choose a strong password for your account.</p>
                            </div>

                            {errorMsg && (
                                <div className="mb-5 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/30 flex gap-3">
                                    <ShieldCheck className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
                                    <p className="text-sm text-red-600 dark:text-red-400 font-medium">{errorMsg}</p>
                                </div>
                            )}

                            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
                                <PwField
                                    label="New Password"
                                    reg={form.register('password')}
                                    error={form.formState.errors.password?.message}
                                    placeholder="Min 8 chars, uppercase, number, symbol"
                                />
                                {pw && <StrengthBar pw={pw} />}
                                <PwField
                                    label="Confirm New Password"
                                    reg={form.register('confirmPassword')}
                                    error={form.formState.errors.confirmPassword?.message}
                                    placeholder="Re-enter your new password"
                                />
                                <button
                                    type="submit"
                                    disabled={state === 'submitting'}
                                    className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold h-11 rounded-xl flex items-center justify-center gap-2 transition-all disabled:opacity-50 shadow-lg shadow-blue-600/20"
                                >
                                    {state === 'submitting'
                                        ? <><Loader2 className="h-5 w-5 animate-spin" /> Updating…</>
                                        : <><span>Reset Password</span><Lock className="h-5 w-5" /></>
                                    }
                                </button>
                            </form>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
