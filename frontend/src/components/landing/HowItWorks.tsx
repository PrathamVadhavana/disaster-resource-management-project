'use client';
import { motion } from 'framer-motion';
import { AlertCircle, BrainCircuit, CheckCircle2 } from 'lucide-react';

const STEPS = [
    {
        icon: AlertCircle,
        title: "1. Request Help",
        desc: "Victims or responders report an incident via app or SMS.",
        color: "text-red-600 dark:text-red-500",
        bg: "bg-red-50 dark:bg-red-500/10",
        border: "border-red-100 dark:border-red-500/20"
    },
    {
        icon: BrainCircuit,
        title: "2. AI Matches Resources",
        desc: "Our engine locates nearest medical, food, and shelter assets.",
        color: "text-blue-600 dark:text-blue-500",
        bg: "bg-blue-50 dark:bg-blue-500/10",
        border: "border-blue-100 dark:border-blue-500/20"
    },
    {
        icon: CheckCircle2,
        title: "3. Aid Delivered",
        desc: "Verified volunteers are dispatched with optimized routes.",
        color: "text-emerald-600 dark:text-emerald-500",
        bg: "bg-emerald-50 dark:bg-emerald-500/10",
        border: "border-emerald-100 dark:border-emerald-500/20"
    }
];

export default function HowItWorks() {
    return (
        <section className="py-24 relative overflow-hidden bg-white dark:bg-slate-950">
            {/* Background Decoration */}
            <div className="absolute inset-0 pointer-events-none">
                <div className="absolute inset-0 bg-slate-50 dark:bg-slate-900/50 -skew-y-3 transform origin-top-left scale-110" />
            </div>

            <div className="relative max-w-7xl mx-auto px-6">
                <div className="text-center mb-16">
                    <h2 className="text-3xl md:text-5xl font-bold mb-4 text-slate-900 dark:text-white">
                        Speed Saves Lives
                    </h2>
                    <p className="text-slate-600 dark:text-slate-400 max-w-2xl mx-auto text-lg font-medium">
                        We cut through the noise to get resources where they are needed instantly.
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-8 relative">
                    {/* Connecting Line (Desktop) - Light Mode: Slate-200, Dark Mode: Slate-700 */}
                    <div className="hidden md:block absolute top-1/2 left-0 w-full h-0.5 bg-gradient-to-r from-transparent via-slate-200 dark:via-slate-700 to-transparent -translate-y-1/2 z-0" />

                    {STEPS.map((step, i) => (
                        <motion.div
                            key={i}
                            initial={{ opacity: 0, y: 30 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ delay: i * 0.2 }}
                            className={`p-8 rounded-3xl border ${step.border} relative z-10 flex flex-col items-center text-center group hover:-translate-y-2 transition-transform duration-300 bg-white dark:bg-slate-900 shadow-sm hover:shadow-lg`}
                        >
                            <div className={`w-16 h-16 rounded-2xl ${step.bg} flex items-center justify-center mb-6 group-hover:scale-110 transition-transform`}>
                                <step.icon className={`w-8 h-8 ${step.color}`} />
                            </div>
                            <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">{step.title}</h3>
                            <p className="text-slate-600 dark:text-slate-400 leading-relaxed font-medium">{step.desc}</p>
                        </motion.div>
                    ))}
                </div>
            </div>
        </section>
    );
}
