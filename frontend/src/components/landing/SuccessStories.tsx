'use client';
import { motion } from 'framer-motion';
import { Quote } from 'lucide-react';
import Image from 'next/image';

const STORIES = [
    {
        quote: "This platform saved lives in our village. We received water and medical kits within 2 hours of the alert.",
        author: "Sarah J.",
        role: "Community Leader, District 9",
        image: "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&q=80&w=100&h=100"
    },
    {
        quote: "As an NGO, the ability to see real-time needs vs. chaos changed how we deploy our fleet.",
        author: "David Chen",
        role: "Logistics Director, AidCorp",
        image: "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?auto=format&fit=crop&q=80&w=100&h=100"
    },
    {
        quote: "Volunteering was finally organized. I knew exactly where to go and who to help.",
        author: "Maria Garcia",
        role: "Certified First Responder",
        image: "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?auto=format&fit=crop&q=80&w=100&h=100"
    }
];

export default function SuccessStories() {
    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {STORIES.map((story, i) => (
                <motion.div
                    key={i}
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.1 }}
                    className="bg-white dark:bg-slate-800/50 p-8 rounded-2xl relative hover:shadow-xl dark:hover:bg-slate-800 transition-all border border-slate-200 dark:border-slate-700/50 shadow-sm"
                >
                    <Quote className="absolute top-6 right-6 w-8 h-8 text-blue-100 dark:text-blue-500/20" />

                    <p className="text-slate-600 dark:text-slate-300 mb-8 leading-relaxed italic relative z-10 font-medium">"{story.quote}"</p>

                    <div className="flex items-center gap-4">
                        <div className="relative w-12 h-12 rounded-full overflow-hidden border-2 border-emerald-500/30">
                            <Image
                                src={story.image}
                                alt={story.author}
                                fill
                                className="object-cover"
                            />
                        </div>
                        <div>
                            <h4 className="text-slate-900 dark:text-white font-bold text-sm">{story.author}</h4>
                            <p className="text-xs text-blue-600 dark:text-blue-400 font-medium">{story.role}</p>
                        </div>
                    </div>
                </motion.div>
            ))}
        </div>
    );
}
