'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { createClient } from '@/lib/supabase/client';
import { Activity, LogOut, LayoutDashboard, User } from 'lucide-react';
import { ThemeToggle } from '@/components/ThemeToggle';
import { cn } from '@/lib/utils';
import { motion, AnimatePresence } from 'framer-motion';

const ROLE_DASHBOARD: Record<string, string> = {
    victim: '/victim',
    ngo: '/ngo',
    donor: '/donor',
    volunteer: '/volunteer',
    admin: '/admin',
};

export default function NavBar() {
    const [user, setUser] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [isScrolled, setIsScrolled] = useState(false);
    const supabase = createClient();
    const router = useRouter();

    const dashboardHref = useMemo(() => {
        const role = user?.user_metadata?.role as string | undefined;
        return ROLE_DASHBOARD[role ?? ''] ?? '/victim';
    }, [user]);

    useEffect(() => {
        // Check initial session
        const checkSession = async () => {
            const { data: { session } } = await supabase.auth.getSession();
            setUser(session?.user ?? null);
            setLoading(false);
        };
        checkSession();

        // Listen for auth changes
        const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
            setUser(session?.user ?? null);
            setLoading(false);
        });

        // Scroll listener for glass effect
        const handleScroll = () => {
            setIsScrolled(window.scrollY > 20);
        };
        window.addEventListener('scroll', handleScroll);

        return () => {
            subscription.unsubscribe();
            window.removeEventListener('scroll', handleScroll);
        };
    }, [supabase]);

    const handleSignOut = async () => {
        await supabase.auth.signOut();
        setUser(null);
        router.push('/');
        router.refresh();
    };

    return (
        <nav className="fixed top-0 w-full z-40 px-4 sm:px-6 py-4 pointer-events-none mt-8">
            <div className="max-w-7xl mx-auto flex items-center justify-between pointer-events-auto">
                {/* Logo */}
                <Link href="/" className={cn(
                    "px-4 py-2 rounded-full flex items-center gap-3 font-bold text-xl transition-all duration-300",
                    isScrolled
                        ? "bg-white/80 dark:bg-slate-900/80 backdrop-blur-md shadow-lg border border-slate-200 dark:border-slate-800"
                        : "bg-white/50 dark:bg-slate-900/50 backdrop-blur-sm"
                )}>
                    <div className="relative">
                        <span className="absolute inline-flex h-full w-full rounded-full bg-blue-600 opacity-20 animate-ping" />
                        <Activity className="text-blue-600 dark:text-blue-500 relative z-10 w-6 h-6" />
                    </div>
                    <span className="text-slate-900 dark:text-white tracking-tight hidden sm:inline">HopeInChaos</span>
                </Link>

                {/* Actions */}
                <div className={cn(
                    "px-3 py-2 rounded-full flex items-center gap-2 transition-all duration-300",
                    isScrolled
                        ? "bg-white/90 dark:bg-slate-900/90 backdrop-blur-md shadow-lg border border-slate-200 dark:border-slate-800"
                        : "bg-white/60 dark:bg-slate-900/60 backdrop-blur-sm border border-transparent"
                )}>
                    <ThemeToggle />

                    <div className="w-px h-6 bg-slate-200 dark:bg-slate-700 mx-1" />

                    {loading ? (
                        <div className="w-20 h-8 rounded-full bg-slate-200 dark:bg-slate-800 animate-pulse" />
                    ) : user ? (
                        <>
                            <Link href={dashboardHref} className="hidden sm:flex items-center gap-2 px-4 py-2 text-sm font-semibold text-slate-700 hover:text-blue-600 dark:text-slate-300 dark:hover:text-blue-400 transition-colors">
                                <LayoutDashboard className="w-4 h-4" />
                                Dashboard
                            </Link>
                            <button
                                onClick={handleSignOut}
                                className="flex items-center gap-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-900 dark:text-white px-4 py-2 rounded-full text-sm font-bold transition-all"
                            >
                                <LogOut className="w-4 h-4" />
                                <span className="hidden sm:inline">Log Out</span>
                            </button>
                        </>
                    ) : (
                        <>
                            <Link href="/login" className="px-4 py-2 text-sm font-semibold text-slate-700 hover:text-blue-600 dark:text-slate-300 dark:hover:text-white transition-colors">
                                Log In
                            </Link>
                            <Link href="/signup" className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-full text-sm font-bold transition-all shadow-md shadow-blue-600/20 hover:shadow-blue-600/30">
                                <User className="w-4 h-4" />
                                <span className="hidden sm:inline">Get Started</span>
                                <span className="sm:hidden">Join</span>
                            </Link>
                        </>
                    )}
                </div>
            </div>
        </nav>
    );
}
