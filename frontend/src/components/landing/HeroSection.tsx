'use client';

import Link from 'next/link';
import Image from 'next/image';
import { ArrowRight, ShieldCheck, HeartHandshake } from 'lucide-react';
import MapPreviewCard from './MapPreviewCard';

export default function HeroSection() {
    return (
        <section className="relative min-h-[95vh] flex items-center justify-center px-6 overflow-hidden pt-20">
            {/* Cinematic Background */}
            <div className="absolute inset-0 z-0">
                <Image
                    src="https://images.unsplash.com/photo-1593113598332-cd288d649433?auto=format&fit=crop&q=80&w=2070"
                    alt="Community Solidarity"
                    fill
                    className="object-cover opacity-100 dark:opacity-40 transition-opacity duration-500"
                    priority
                />
                {/* Heavy Gradient Overlay for Text Visibility */}
                {/* Heavy Gradient Overlay - Reduced opacity for visibility */}
                <div className="absolute inset-0 bg-gradient-to-b from-slate-50/70 via-slate-50/60 to-white dark:from-slate-900/80 dark:via-slate-900/70 dark:to-slate-950" />
            </div>

            <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-16 items-center relative z-10">
                <div className="space-y-8 text-center lg:text-left pt-10 lg:pt-0">
                    <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400 text-xs font-bold uppercase tracking-wider border border-blue-200 dark:border-blue-500/20">
                        <span className="w-2 h-2 rounded-full bg-blue-600 dark:bg-blue-500 animate-pulse" />
                        System Operational • Global Reach
                    </div>

                    <h1 className="text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.1] text-slate-900 dark:text-white">
                        Hope in <br />
                        <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-600 dark:from-blue-400 dark:via-emerald-400 dark:to-blue-400 bg-[length:200%_auto] animate-shimmer">
                            Chaos
                        </span>
                    </h1>

                    <p className="text-lg sm:text-xl text-slate-600 dark:text-slate-300 max-w-lg leading-relaxed mx-auto lg:mx-0 font-medium">
                        The real-time disaster relief coordination platform connecting <span className="text-slate-900 dark:text-white font-bold decoration-blue-500 underline decoration-2 underline-offset-2">victims, NGOs, and volunteers</span> when seconds count.
                    </p>

                    <div className="flex flex-col sm:flex-row gap-4 justify-center lg:justify-start">
                        <Link
                            href="/signup?role=victim"
                            className="group bg-red-600 hover:bg-red-700 text-white px-8 py-4 rounded-2xl font-bold text-lg flex items-center justify-center gap-3 transition-all hover:scale-105 shadow-xl shadow-red-600/20 ring-offset-2 focus:ring-2 ring-red-600"
                        >
                            <ShieldCheck className="w-6 h-6 group-hover:animate-bounce" />
                            I Need Help
                        </Link>
                        <Link
                            href="/signup"
                            className="group bg-white dark:bg-slate-800 text-slate-900 dark:text-white hover:bg-slate-50 dark:hover:bg-slate-700 px-8 py-4 rounded-2xl font-bold text-lg flex items-center justify-center gap-3 transition-all hover:scale-105 border border-slate-200 dark:border-slate-700 shadow-lg"
                        >
                            <HeartHandshake className="w-6 h-6 text-emerald-600 dark:text-emerald-400" />
                            I Want to Help
                        </Link>
                    </div>

                    <div className="flex items-center justify-center lg:justify-start gap-8 pt-8 border-t border-slate-200 dark:border-slate-800/50">
                        <div>
                            <p className="text-3xl font-bold text-slate-900 dark:text-white">12k+</p>
                            <p className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400 font-bold mt-1">Lives Impacted</p>
                        </div>
                        <div className="w-px h-12 bg-slate-200 dark:bg-slate-800" />
                        <div>
                            <p className="text-3xl font-bold text-slate-900 dark:text-white">45min</p>
                            <p className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400 font-bold mt-1">Avg Response</p>
                        </div>
                        <div className="w-px h-12 bg-slate-200 dark:bg-slate-800" />
                        <div>
                            <p className="text-3xl font-bold text-slate-900 dark:text-white">Top 1%</p>
                            <p className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400 font-bold mt-1">NGO Efficiency</p>
                        </div>
                    </div>
                </div>

                {/* Right Column: Enhanced Map Visual */}
                <div className="perspective-1000 hidden lg:block">
                    <div className="transform rotate-y-[-5deg] rotate-x-[5deg] hover:rotate-0 transition-transform duration-700 ease-out">
                        <MapPreviewCard />

                        {/* Decorative floating elements */}
                        <div className="absolute -z-10 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[120%] h-[120%] bg-blue-500/20 blur-[100px] rounded-full opacity-30 pointer-events-none" />
                    </div>
                </div>
            </div>

            {/* Scroll Indicator */}
            <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 opacity-50 animate-bounce">
                <span className="text-xs uppercase tracking-widest text-slate-500 dark:text-slate-400 font-semibold">Scroll to Explore</span>
                <ArrowRight className="rotate-90 w-4 h-4 text-slate-500 dark:text-slate-400" />
            </div>
        </section>
    );
}
