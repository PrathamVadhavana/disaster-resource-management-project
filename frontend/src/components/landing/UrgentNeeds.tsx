'use client';
import { motion } from 'framer-motion';
import { Droplets, Pill, Home, Battery } from 'lucide-react';

const NEEDS = [
    { type: 'Water', amount: '500L', location: 'Zone A', urgency: 'Critical', icon: Droplets, color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/20' },
    { type: 'Medical', amount: '200 Kits', location: 'Sector 4', urgency: 'High', icon: Pill, color: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-900/20' },
    { type: 'Shelter', amount: '50 Tents', location: 'North Camp', urgency: 'Medium', icon: Home, color: 'text-orange-600 dark:text-orange-400', bg: 'bg-orange-50 dark:bg-orange-900/20' },
    { type: 'Power', amount: '10 Generators', location: 'Hospital', urgency: 'Critical', icon: Battery, color: 'text-yellow-600 dark:text-yellow-400', bg: 'bg-yellow-50 dark:bg-yellow-900/20' },
    { type: 'Water', amount: '1000L', location: 'Zone B', urgency: 'High', icon: Droplets, color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/20' },
];

export default function UrgentNeeds() {
    return (
        <div className="w-full overflow-hidden py-8">
            <h3 className="text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest mb-6 px-4">Live Urgent Requests</h3>
            <motion.div
                className="flex gap-4 px-4"
                drag="x"
                dragConstraints={{ right: 0, left: -400 }}
            >
                {NEEDS.map((need, i) => (
                    <div key={i} className="min-w-[220px] bg-white dark:bg-slate-800/50 p-5 rounded-xl border border-slate-200 dark:border-slate-700 flex flex-col gap-4 group hover:border-blue-500/50 transition-colors shadow-sm cursor-grab active:cursor-grabbing">
                        <div className="flex justify-between items-start">
                            <div className={`p-2 rounded-lg ${need.bg} ${need.color}`}>
                                <need.icon className="w-5 h-5" />
                            </div>
                            <span className="text-[10px] font-bold px-2 py-1 rounded bg-red-100 text-red-600 dark:bg-red-500/20 dark:text-red-400 uppercase border border-red-200 dark:border-transparent">{need.urgency}</span>
                        </div>
                        <div>
                            <h4 className="text-slate-900 dark:text-white font-bold text-lg">{need.amount} {need.type}</h4>
                            <p className="text-slate-500 dark:text-slate-400 text-xs mt-1 font-medium">Needed at {need.location}</p>
                        </div>
                    </div>
                ))}
            </motion.div>
        </div>
    );
}
