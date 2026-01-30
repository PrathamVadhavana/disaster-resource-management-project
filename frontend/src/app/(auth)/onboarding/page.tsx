'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { createClient } from '@/lib/supabase/client';
import { UserRole, ROLE_METADATA } from '@/lib/auth/authTypes';
import { Check, Loader2, ArrowRight, ShieldCheck } from 'lucide-react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

export default function OnboardingPage() {
    const [selectedRole, setSelectedRole] = useState<UserRole | null>(null);
    const [loading, setLoading] = useState(false);
    const [initializing, setInitializing] = useState(true);
    const router = useRouter();
    const supabase = createClient();

    useEffect(() => {
        const checkUser = async () => {
            const { data: { user } } = await supabase.auth.getUser();
            if (!user) {
                router.push('/login');
                return;
            }
            // Ideally check if profile exists and has role
            // For now, we assume if they are here, they need a role or we force update
            setInitializing(false);
        };
        checkUser();
    }, [router, supabase]);

    const handleRoleSelect = (role: UserRole) => {
        setSelectedRole(role);
    };

    const handleSubmit = async () => {
        if (!selectedRole) return;
        setLoading(true);

        try {
            const { data: { user } } = await supabase.auth.getUser();
            if (!user) throw new Error('No user found');

            // Update public.users
            const { error } = await supabase
                .from('users')
                .upsert({
                    id: user.id,
                    role: selectedRole,
                    updated_at: new Date().toISOString(),
                });

            if (error) throw error;

            // Also update auth metadata for faster access if using JWT claims setup
            await supabase.auth.updateUser({
                data: { role: selectedRole }
            });

            router.push('/dashboard');
            router.refresh();
        } catch (error: any) {
            console.error('Error updating role:', error);
            alert('Failed to save role. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    if (initializing) {
        return (
            <div className="min-h-screen bg-[#0F172A] flex items-center justify-center">
                <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#0F172A] py-12 px-4 sm:px-6 lg:px-8">
            <div className="max-w-5xl mx-auto space-y-12">
                <div className="text-center space-y-4">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="inline-flex items-center justify-center p-3 bg-blue-500/10 rounded-full mb-4"
                    >
                        <ShieldCheck className="w-8 h-8 text-blue-400" />
                    </motion.div>
                    <motion.h1
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.1 }}
                        className="text-4xl font-bold text-white tracking-tight"
                    >
                        What is your role in this crisis?
                    </motion.h1>
                    <motion.p
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.2 }}
                        className="text-xl text-slate-400 max-w-2xl mx-auto"
                    >
                        Select the role that best describes how you will use the platform. This helps us customize your experience and permissions.
                    </motion.p>
                </div>

                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 }}
                    className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
                >
                    {Object.entries(ROLE_METADATA).map(([role, meta], index) => {
                        const isSelected = selectedRole === role;
                        return (
                            <div
                                key={role}
                                onClick={() => handleRoleSelect(role as UserRole)}
                                className={cn(
                                    "relative p-6 rounded-xl border-2 cursor-pointer transition-all duration-200 group bg-slate-800/50 backdrop-blur-sm",
                                    isSelected
                                        ? "border-blue-500 bg-blue-500/10 shadow-xl shadow-blue-500/10 scale-[1.02]"
                                        : "border-slate-700 hover:border-slate-500 hover:bg-slate-800"
                                )}
                            >
                                {isSelected && (
                                    <div className="absolute top-4 right-4 bg-blue-500 rounded-full p-1">
                                        <Check className="w-3 h-3 text-white" />
                                    </div>
                                )}

                                <div className="flex flex-col h-full space-y-4">
                                    <div className="text-4xl">{meta.icon}</div>
                                    <div>
                                        <h3 className={cn(
                                            "text-lg font-bold mb-1 group-hover:text-white transition-colors",
                                            isSelected ? "text-white" : "text-slate-200"
                                        )}>
                                            {meta.label}
                                        </h3>
                                        <p className="text-sm text-slate-400 leading-relaxed">
                                            {meta.description}
                                        </p>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </motion.div>

                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.5 }}
                    className="flex justify-center pt-8"
                >
                    <button
                        onClick={handleSubmit}
                        disabled={!selectedRole || loading}
                        className={cn(
                            "flex items-center px-8 py-4 rounded-full font-bold text-lg transition-all duration-200 shadow-lg",
                            selectedRole
                                ? "bg-blue-600 hover:bg-blue-500 text-white shadow-blue-500/25 hover:scale-105 transform"
                                : "bg-slate-800 text-slate-500 cursor-not-allowed"
                        )}
                    >
                        {loading ? (
                            <Loader2 className="w-6 h-6 animate-spin mr-2" />
                        ) : null}
                        Continue to Dashboard
                        {!loading && <ArrowRight className="ml-2 w-5 h-5" />}
                    </button>
                </motion.div>
            </div>
        </div>
    );
}
