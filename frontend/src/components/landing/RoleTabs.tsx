'use client';
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { UserRole } from '@/lib/auth/authTypes';
import { Shield, Truck, Heart, Users } from 'lucide-react';
import { cn } from '@/lib/utils';

const ROLE_CONTENT = [
    {
        role: UserRole.VICTIM,
        label: "For Those in Need",
        icon: Shield,
        title: "Help arrives faster when we know where you are.",
        features: [
            "One-tap Emergency SOS",
            "Real-time resource tracking",
            "Offline-first reporting"
        ],
        color: "bg-red-500",
        textColor: "text-red-500"
    },
    {
        role: UserRole.NGO,
        label: "For NGOs",
        icon: Truck,
        title: "Coordinate massive operations without chaos.",
        features: [
            "Fleet & inventory management",
            "Volunteer allocation heatmaps",
            "Impact analytics dashboard"
        ],
        color: "bg-blue-500",
        textColor: "text-blue-500"
    },
    {
        role: UserRole.DONOR,
        label: "For Donors",
        icon: Heart,
        title: "See exactly where your help goes.",
        features: [
            "Transparent supply chain tracking",
            "Direct-to-victim aid flow",
            "Verified impact reports"
        ],
        color: "bg-emerald-500",
        textColor: "text-emerald-500"
    },
    {
        role: UserRole.VOLUNTEER,
        label: "For Volunteers",
        icon: Users,
        title: "Your skills, deployed where they matter most.",
        features: [
            "Skill-based task matching",
            "Team coordination tools",
            "Digital ID & verification"
        ],
        color: "bg-orange-500",
        textColor: "text-orange-500"
    }
];

export default function RoleTabs() {
    const [activeTab, setActiveTab] = useState(0);

    return (
        <div className="w-full max-w-6xl mx-auto px-4">
            <div className="flex flex-wrap justify-center gap-2 mb-12">
                {ROLE_CONTENT.map((content, index) => (
                    <button
                        key={index}
                        onClick={() => setActiveTab(index)}
                        className={cn(
                            "px-6 py-3 rounded-full font-medium transition-all duration-300 border",
                            activeTab === index
                                ? `${content.color} text-white border-transparent`
                                : "bg-transparent text-slate-400 border-slate-700 hover:border-slate-500"
                        )}
                    >
                        {content.label}
                    </button>
                ))}
            </div>

            <div className="min-h-[400px]">
                <AnimatePresence mode="wait">
                    <motion.div
                        key={activeTab}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        transition={{ duration: 0.3 }}
                        className="grid grid-cols-1 md:grid-cols-2 gap-12 items-center"
                    >
                        <div className="space-y-6">
                            <div className={cn("p-4 rounded-2xl w-fit bg-slate-800/50", ROLE_CONTENT[activeTab].textColor)}>
                                {(() => {
                                    const Icon = ROLE_CONTENT[activeTab].icon;
                                    return <Icon className="w-8 h-8" />;
                                })()}
                            </div>
                            <h2 className="text-4xl md:text-5xl font-bold text-white leading-tight">
                                {ROLE_CONTENT[activeTab].title}
                            </h2>
                            <ul className="space-y-4">
                                {ROLE_CONTENT[activeTab].features.map((feature, i) => (
                                    <li key={i} className="flex items-center gap-3 text-slate-300 text-lg">
                                        <div className={cn("w-2 h-2 rounded-full", ROLE_CONTENT[activeTab].color)} />
                                        {feature}
                                    </li>
                                ))}
                            </ul>
                        </div>

                        {/* Bento Grid Visual for Feature */}
                        <div className="h-[400px] w-full bg-slate-800/50 rounded-3xl border border-slate-700 p-6 relative overflow-hidden backdrop-blur-sm">
                            <div className={cn("absolute inset-0 opacity-5 bg-gradient-to-br from-white to-transparent", ROLE_CONTENT[activeTab].color)} />

                            {/* Mock UI Elements */}
                            <div className="grid grid-cols-2 gap-4 h-full">
                                <div className="bg-slate-900/80 rounded-2xl p-4 border border-slate-600/50 col-span-2 h-[45%] animate-pulse">
                                    <div className="h-4 w-1/3 bg-slate-700 rounded mb-4" />
                                    <div className="h-2 w-full bg-slate-700/50 rounded mb-2" />
                                    <div className="h-2 w-2/3 bg-slate-700/50 rounded" />
                                </div>
                                <div className="bg-slate-900/80 rounded-2xl p-4 border border-slate-600/50 h-[50%]">
                                    <div className="h-8 w-8 rounded-full bg-slate-700 mb-4" />
                                </div>
                                <div className="bg-slate-900/80 rounded-2xl p-4 border border-slate-600/50 h-[50%]">
                                    <div className="h-full w-full bg-slate-700/20 rounded" />
                                </div>
                            </div>
                        </div>
                    </motion.div>
                </AnimatePresence>
            </div>
        </div>
    );
}
