'use client';
import { motion } from 'framer-motion';
import { Quote } from 'lucide-react';
import Image from 'next/image';
import { useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Testimonial {
    id: string;
    author_name: string;
    author_role: string | null;
    quote: string;
    image_url: string | null;
}

export default function SuccessStories() {
    const [stories, setStories] = useState<Testimonial[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch(`${API}/api/admin/testimonials`)
            .then(r => r.ok ? r.json() : [])
            .then(setStories)
            .catch(() => setStories([]))
            .finally(() => setLoading(false));
    }, []);

    if (loading) {
        return (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                {[0, 1, 2].map(i => (
                    <div key={i} className="bg-white dark:bg-slate-800/50 p-8 rounded-2xl border border-slate-200 dark:border-slate-700/50 animate-pulse h-48" />
                ))}
            </div>
        );
    }

    if (stories.length === 0) {
        return (
            <div className="text-center py-12 text-slate-500 dark:text-slate-400">
                <Quote className="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p className="font-medium">No testimonials yet</p>
                <p className="text-sm">Stories from our community will appear here.</p>
            </div>
        );
    }

    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {stories.map((story, i) => (
                <motion.div
                    key={story.id}
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.1 }}
                    className="bg-white dark:bg-slate-800/50 p-8 rounded-2xl relative hover:shadow-xl dark:hover:bg-slate-800 transition-all border border-slate-200 dark:border-slate-700/50 shadow-sm"
                >
                    <Quote className="absolute top-6 right-6 w-8 h-8 text-blue-100 dark:text-blue-500/20" />

                    <p className="text-slate-600 dark:text-slate-300 mb-8 leading-relaxed italic relative z-10 font-medium">&ldquo;{story.quote}&rdquo;</p>

                    <div className="flex items-center gap-4">
                        {story.image_url ? (
                            <div className="relative w-12 h-12 rounded-full overflow-hidden border-2 border-emerald-500/30">
                                <Image
                                    src={story.image_url}
                                    alt={story.author_name}
                                    fill
                                    className="object-cover"
                                />
                            </div>
                        ) : (
                            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-blue-500 to-emerald-500 flex items-center justify-center text-white font-bold text-lg border-2 border-emerald-500/30">
                                {story.author_name.charAt(0).toUpperCase()}
                            </div>
                        )}
                        <div>
                            <h4 className="text-slate-900 dark:text-white font-bold text-sm">{story.author_name}</h4>
                            {story.author_role && (
                                <p className="text-xs text-blue-600 dark:text-blue-400 font-medium">{story.author_role}</p>
                            )}
                        </div>
                    </div>
                </motion.div>
            ))}
        </div>
    );
}
