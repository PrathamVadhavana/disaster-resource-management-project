'use client';

import { motion } from 'framer-motion';
import { Shield, Truck, HandHeart, Heart, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { UserRole } from '@/lib/auth/authTypes';

const ROLES = [
    {
        role: UserRole.VICTIM,
        label: "For Victims",
        icon: Shield,
        description: "Request aid instantly. Share your location securely. get verified status updates.",
        href: "/signup?role=victim",
        color: "blue"
    },
    {
        role: UserRole.NGO,
        label: "For NGOs",
        icon: Truck,
        description: "Coordinate resources. Visualize impact. Eliminate supply chain bottlenecks.",
        href: "/signup?role=ngo",
        color: "blue"
    },
    {
        role: UserRole.DONOR,
        label: "For Donors",
        icon: HandHeart,
        description: "Track your contributions. See real-time impact. Verified transparency.",
        href: "/signup?role=donor",
        color: "blue"
    },
    {
        role: UserRole.VOLUNTEER,
        label: "For Volunteers",
        icon: Heart,
        description: "Join verified missions. Get safe routes. Make a direct difference.",
        href: "/signup?role=volunteer",
        color: "blue"
    },
];

export default function RoleCards() {
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 px-4">
            {ROLES.map((role, i) => (
                <RoleCard key={role.role} data={role} index={i} />
            ))}
        </div>
    );
}

function RoleCard({ data, index }: { data: typeof ROLES[0], index: number }) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: index * 0.1 }}
            className={cn(
                "group relative h-[340px] rounded-2xl p-8 flex flex-col justify-between transition-all duration-300",
                // Light Mode: Pure White, Subtle Border, Soft Shadow
                "bg-white border border-slate-200 shadow-sm",
                // Dark Mode: Deep Slate, Subtle Border
                "dark:bg-slate-900 dark:border-slate-800",
                // Hover State: Lift, Blue Border, deeper shadow
                "hover:-translate-y-1 hover:shadow-xl hover:border-blue-600/30 dark:hover:border-blue-500/50"
            )}
        >
            <div>
                <div className={cn(
                    "w-14 h-14 rounded-xl flex items-center justify-center mb-6 transition-colors duration-300",
                    // Light: Blue-50 background, Blue-600 icon
                    "bg-blue-50 text-blue-600",
                    // Dark: Blue-900/20 background, Blue-400 icon
                    "dark:bg-blue-500/10 dark:text-blue-400",
                    // Group Hover: Stronger blue
                    "group-hover:bg-blue-600 group-hover:text-white dark:group-hover:bg-blue-600"
                )}>
                    <data.icon className="w-7 h-7" />
                </div>

                <h3 className="text-2xl font-bold mb-3 text-slate-900 dark:text-white">
                    {data.label}
                </h3>

                <p className="text-slate-600 dark:text-slate-300 font-medium leading-relaxed">
                    {data.description}
                </p>
            </div>

            <div className="flex items-center gap-2 font-bold text-sm text-blue-600 dark:text-blue-400 group-hover:translate-x-1 transition-transform cursor-pointer">
                <span>Get Started</span>
                <ArrowRight className="w-4 h-4" />
            </div>
        </motion.div>
    )
}
