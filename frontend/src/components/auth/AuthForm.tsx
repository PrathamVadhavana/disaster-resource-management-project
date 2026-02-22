'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { createClient } from '@/lib/supabase/client';
import { useAuth } from '@/lib/auth-provider';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Loader2, Mail, ShieldCheck, ArrowRight, UserCircle, CheckCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { PasswordInput } from '@/components/ui/PasswordInput';
import { UserRole } from '@/lib/auth/authTypes';

// --- Validation Schemas ---

const loginSchema = z.object({
    email: z.string().email('Please enter a valid email address'),
    password: z.string().min(1, 'Password is required'),
});

const signUpSchema = z.object({
    email: z.string().email('Please enter a valid email address'),
    password: z
        .string()
        .min(8, 'Password must be at least 8 characters')
        .regex(/[A-Z]/, 'Password must contain at least one uppercase letter')
        .regex(/[0-9]/, 'Password must contain at least one number')
        .regex(/[^A-Za-z0-9]/, 'Password must contain at least one special character'),
    fullName: z.string().min(2, 'Full name is required'),
    role: z.nativeEnum(UserRole, { required_error: 'Please select a role' }).refine(
        (val) => val !== UserRole.ADMIN,
        { message: 'Invalid role selection' }
    ),
});

const otpSchema = z.object({
    token: z.string().length(6, 'OTP must be exactly 6 digits').regex(/^\d+$/, 'OTP must be numbers only'),
});

type LoginValues = z.infer<typeof loginSchema>;
type SignUpValues = z.infer<typeof signUpSchema>;
type OtpValues = z.infer<typeof otpSchema>;

interface AuthFormProps {
    initialView?: 'login' | 'signup';
}

export default function AuthForm({ initialView = 'login' }: AuthFormProps) {
    const [view, setView] = useState<'login' | 'signup'>(initialView);
    const [step, setStep] = useState<'CREDENTIALS' | 'VERIFICATION'>('CREDENTIALS');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [emailToVerify, setEmailToVerify] = useState<string>('');

    const supabase = createClient();
    const router = useRouter();
    const { signIn } = useAuth();

    // Login Form
    const loginForm = useForm<LoginValues>({
        resolver: zodResolver(loginSchema),
        defaultValues: { email: '', password: '' },
    });

    // Signup Form
    const signUpForm = useForm<SignUpValues>({
        resolver: zodResolver(signUpSchema),
        defaultValues: { email: '', password: '', fullName: '', role: undefined },
    });

    // OTP Form
    const otpForm = useForm<OtpValues>({
        resolver: zodResolver(otpSchema),
        defaultValues: { token: '' },
    });

    const onLogin = async (data: LoginValues) => {
        setIsLoading(true);
        setError(null);
        try {
            // Use AuthProvider's signIn which handles profile-completion redirect
            const { error } = await signIn(data.email, data.password);
            if (error) throw error;
            // Redirect is handled by signIn in auth-provider
        } catch (err: any) {
            setError(err.message || 'Failed to login');
            setIsLoading(false);
        }
    };

    const onSignUp = async (data: SignUpValues) => {
        setIsLoading(true);
        setError(null);
        try {
            // 1. Check if user exists using our secure RPC
            let status = null;
            try {
                const { data: rpcData, error: rpcError } = await (supabase.rpc as any)('check_user_status', {
                    p_email: data.email
                });

                if (!rpcError) {
                    status = rpcData;
                }
                // If RPC fails (function might be missing), we let Supabase auth handle validation
            } catch {
                // RPC not available, continue with signup
            }

            if (status?.exists) {
                throw new Error('User already exists. Please log in.');
            }

            // 2. Proceed with Signup
            const { error } = await supabase.auth.signUp({
                email: data.email,
                password: data.password,
                options: {
                    data: {
                        full_name: data.fullName,
                        role: data.role,
                    },
                },
            });
            if (error) throw error;
            setEmailToVerify(data.email);
            setStep('VERIFICATION');
        } catch (err: any) {
            console.error('Signup error:', err);
            setError(err.message || 'Failed to sign up');
        } finally {
            setIsLoading(false);
        }
    };

    const onVerifyOtp = async (data: OtpValues) => {
        setIsLoading(true);
        setError(null);
        try {
            const { data: authData, error } = await supabase.auth.verifyOtp({
                email: emailToVerify,
                token: data.token,
                type: 'signup',
            });
            if (error) throw error;
            if (authData.user) {
                // After email verification, redirect to onboarding for new users
                router.push('/onboarding');
                router.refresh();
            }
        } catch (err: any) {
            setError(err.message || 'Invalid or expired OTP');
            setIsLoading(false);
        }
    };

    const handleGoogleAuth = async () => {
        setError(null);
        const { error } = await supabase.auth.signInWithOAuth({
            provider: 'google',
            options: {
                redirectTo: `${window.location.origin}/auth/callback`,
            },
        });
        if (error) setError(error.message);
    };

    const toggleView = () => {
        setView(view === 'login' ? 'signup' : 'login');
        setError(null);
        setStep('CREDENTIALS');
    };

    // --- Google OAuth Button (shared between login and signup) ---
    const GoogleButton = () => (
        <>
            <button
                type="button"
                onClick={handleGoogleAuth}
                className="w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 font-bold h-11 rounded-xl flex items-center justify-center gap-2 hover:bg-slate-50 dark:hover:bg-slate-750 transition-all"
            >
                <svg className="w-5 h-5" viewBox="0 0 24 24">
                    <path
                        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                        fill="#4285F4"
                    />
                    <path
                        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                        fill="#34A853"
                    />
                    <path
                        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                        fill="#FBBC05"
                    />
                    <path
                        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                        fill="#EA4335"
                    />
                </svg>
                Continue with Google
            </button>

            <div className="relative">
                <div className="absolute inset-0 flex items-center">
                    <span className="w-full border-t border-slate-200 dark:border-slate-800" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                    <span className="bg-white dark:bg-slate-900 px-2 text-slate-500">Or continue with email</span>
                </div>
            </div>
        </>
    );

    return (
        <div className="w-full max-w-md mx-auto p-8 rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl transition-all">
            <div className="text-center mb-8">
                <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">
                    {step === 'VERIFICATION'
                        ? 'Verify Email'
                        : view === 'login' ? 'Welcome Back' : 'Create Account'}
                </h2>
                <p className="text-sm text-slate-500 dark:text-slate-400">
                    {step === 'VERIFICATION'
                        ? `Enter the code sent to ${emailToVerify}`
                        : view === 'login'
                            ? 'Enter your credentials to access your account'
                            : 'Join the community to assist or receive aid'}
                </p>
            </div>

            {error && (
                <div className="mb-6 p-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/30 flex items-start gap-3">
                    <ShieldCheck className="w-5 h-5 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
                    <p className="text-sm text-red-600 dark:text-red-400 font-medium">{error}</p>
                </div>
            )}

            {step === 'VERIFICATION' ? (
                // --- OTP VERIFICATION FORM ---
                <form onSubmit={otpForm.handleSubmit(onVerifyOtp)} className="space-y-6">
                    <div className="space-y-2">
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300">OTP Code</label>
                        <input
                            {...otpForm.register('token')}
                            maxLength={6}
                            className="text-center text-2xl tracking-[0.5em] font-mono h-14 w-full rounded-xl border border-slate-200 bg-white dark:bg-slate-950 dark:border-slate-800 focus:ring-2 focus:ring-blue-600 focus:outline-none transition-all"
                            placeholder="000000"
                        />
                        {otpForm.formState.errors.token && (
                            <p className="text-xs text-center text-red-500 font-medium">{otpForm.formState.errors.token.message}</p>
                        )}
                    </div>

                    <button
                        type="submit"
                        disabled={isLoading}
                        className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold h-11 rounded-xl flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-emerald-600/20"
                    >
                        {isLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : <>Verify Email <CheckCircle className="h-5 w-5" /></>}
                    </button>

                    <div className="flex flex-col gap-2">
                        <button
                            type="button"
                            disabled={isLoading}
                            onClick={async () => {
                                setIsLoading(true);
                                try {
                                    const { error } = await supabase.auth.resend({
                                        type: 'signup',
                                        email: emailToVerify,
                                    });
                                    if (error) {
                                        if (error.status === 429) {
                                            throw new Error('Please wait 60 seconds before requesting another code.');
                                        }
                                        throw error;
                                    }
                                    alert('New code sent! Please check your spam folder.');
                                } catch (err: any) {
                                    console.error("Resend Error:", err);
                                    setError(err.message || 'Failed to resend code');
                                } finally {
                                    setIsLoading(false);
                                }
                            }}
                            className="w-full text-sm font-bold text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
                        >
                            Resend Code
                        </button>

                        <button
                            type="button"
                            onClick={() => setStep('CREDENTIALS')}
                            className="w-full text-sm text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 underline underline-offset-4"
                        >
                            Wrong email? Go back
                        </button>
                    </div>
                </form>
            ) : view === 'login' ? (
                // --- LOGIN FORM ---
                <form onSubmit={loginForm.handleSubmit(onLogin)} className="space-y-5">
                    <GoogleButton />

                    <div className="space-y-2">
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Email Address</label>
                        <div className="relative">
                            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400" />
                            <input
                                {...loginForm.register('email')}
                                type="email"
                                className="pl-10 flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm placeholder:text-slate-500 focus-visible:outline-none focus:ring-2 focus:ring-blue-600 transition-all dark:border-slate-800 dark:bg-slate-950 dark:placeholder:text-slate-400 dark:focus:ring-blue-500"
                                placeholder="you@example.com"
                            />
                        </div>
                        {loginForm.formState.errors.email && (
                            <p className="text-xs text-red-500 font-medium">{loginForm.formState.errors.email.message}</p>
                        )}
                    </div>
                    <div className="space-y-2">
                        <div className="flex justify-between items-center">
                            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Password</label>
                            <a href="#" className="text-xs text-blue-600 hover:text-blue-500 font-medium">Forgot password?</a>
                        </div>
                        <PasswordInput
                            {...loginForm.register('password')}
                            placeholder="Enter your password"
                        />
                        {loginForm.formState.errors.password && (
                            <p className="text-xs text-red-500 font-medium">{loginForm.formState.errors.password.message}</p>
                        )}
                    </div>
                    <button
                        type="submit"
                        disabled={isLoading}
                        className="w-full mt-6 bg-blue-600 hover:bg-blue-700 text-white font-bold h-11 rounded-xl flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-blue-600/20"
                    >
                        {isLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : <>Log In <ArrowRight className="h-5 w-5" /></>}
                    </button>
                    <div className="pt-4 text-center text-sm">
                        <span className="text-slate-500 dark:text-slate-400">Don't have an account? </span>
                        <button type="button" onClick={toggleView} className="text-blue-600 font-bold hover:underline">Sign up</button>
                    </div>
                </form>
            ) : (
                // --- SIGNUP FORM ---
                <form onSubmit={signUpForm.handleSubmit(onSignUp)} className="space-y-5">
                    <GoogleButton />

                    <div className="space-y-2">
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Full Name</label>
                        <div className="relative">
                            <UserCircle className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400" />
                            <input
                                {...signUpForm.register('fullName')}
                                className="pl-10 flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm placeholder:text-slate-500 focus-visible:outline-none focus:ring-2 focus:ring-blue-600 transition-all dark:border-slate-800 dark:bg-slate-950 dark:placeholder:text-slate-400 dark:focus:ring-blue-500"
                                placeholder="John Doe"
                                suppressHydrationWarning
                            />
                        </div>
                        {signUpForm.formState.errors.fullName && (
                            <p className="text-xs text-red-500 font-medium">{signUpForm.formState.errors.fullName.message}</p>
                        )}
                    </div>

                    <div className="space-y-2">
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Email Address</label>
                        <div className="relative">
                            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400" />
                            <input
                                {...signUpForm.register('email')}
                                type="email"
                                className="pl-10 flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm placeholder:text-slate-500 focus-visible:outline-none focus:ring-2 focus:ring-blue-600 transition-all dark:border-slate-800 dark:bg-slate-950 dark:placeholder:text-slate-400 dark:focus:ring-blue-500"
                                placeholder="you@example.com"
                            />
                        </div>
                        {signUpForm.formState.errors.email && (
                            <p className="text-xs text-red-500 font-medium">{signUpForm.formState.errors.email.message}</p>
                        )}
                    </div>

                    <div className="space-y-2">
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Password</label>
                        <PasswordInput
                            {...signUpForm.register('password')}
                            placeholder="Min 8 chars, 1 upper, 1 special"
                        />
                        {signUpForm.formState.errors.password && (
                            <p className="text-xs text-red-500 font-medium">{signUpForm.formState.errors.password.message}</p>
                        )}
                    </div>

                    <div className="space-y-2">
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                            I am joining as a... <span className="text-red-500">*</span>
                        </label>
                        <div className="grid grid-cols-2 gap-3">
                            {[
                                { value: UserRole.VICTIM, label: 'Victim', desc: 'I need help' },
                                { value: UserRole.VOLUNTEER, label: 'Volunteer', desc: 'I want to help' },
                                { value: UserRole.NGO, label: 'NGO', desc: 'Organization' },
                                { value: UserRole.DONOR, label: 'Donor', desc: 'Giving aid' },
                            ].map((role) => (
                                <label
                                    key={role.value}
                                    className={cn(
                                        "cursor-pointer rounded-xl border p-3 flex flex-col items-start gap-1 transition-all hover:bg-slate-50 dark:hover:bg-slate-800",
                                        signUpForm.watch('role') === role.value
                                            ? "border-blue-600 bg-blue-50/50 dark:bg-blue-900/10 ring-1 ring-blue-600"
                                            : "border-slate-200 dark:border-slate-700 bg-transparent"
                                    )}
                                >
                                    <input type="radio" value={role.value} {...signUpForm.register('role')} className="sr-only" />
                                    <span className={cn(
                                        "text-sm font-bold",
                                        signUpForm.watch('role') === role.value ? "text-blue-700 dark:text-blue-400" : "text-slate-700 dark:text-slate-300"
                                    )}>{role.label}</span>
                                    <span className="text-xs text-slate-500 dark:text-slate-400">{role.desc}</span>
                                </label>
                            ))}
                        </div>
                        {signUpForm.formState.errors.role && (
                            <p className="text-xs text-red-500 font-medium">{signUpForm.formState.errors.role.message}</p>
                        )}
                    </div>

                    <button
                        type="submit"
                        disabled={isLoading}
                        className="w-full mt-6 bg-blue-600 hover:bg-blue-700 text-white font-bold h-11 rounded-xl flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-blue-600/20"
                    >
                        {isLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : <>Create Account <ArrowRight className="h-5 w-5" /></>}
                    </button>
                    <div className="pt-4 text-center text-sm">
                        <span className="text-slate-500 dark:text-slate-400">Already have an account? </span>
                        <button type="button" onClick={toggleView} className="text-blue-600 font-bold hover:underline">Log in</button>
                    </div>
                </form>
            )}
        </div>
    );
}
