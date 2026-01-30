import Link from 'next/link';
import { Activity } from 'lucide-react';
import NavBar from '@/components/layout/NavBar';
import Ticker from '@/components/landing/Ticker';
import UrgentNeeds from '@/components/landing/UrgentNeeds';
import SuccessStories from '@/components/landing/SuccessStories';
import HowItWorks from '@/components/landing/HowItWorks';
import HeroSection from '@/components/landing/HeroSection';
import RoleCards from '@/components/landing/RoleCards';
import { ThemeToggle } from '@/components/ThemeToggle';

export default function LandingPage() {
  return (
    <div className="min-h-screen w-full bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-50 overflow-x-hidden selection:bg-blue-100 dark:selection:bg-blue-900">
      {/* Ticker */}
      <div className="fixed top-0 z-50 w-full border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
        <Ticker />
      </div>

      {/* Navbar - Now a standalone client component */}
      <NavBar />

      <main className="pt-0">

        <HeroSection />

        <HowItWorks />

        {/* Urgent Needs Section - Light Grey Background in Light Mode for separation */}
        <section className="py-20 border-y border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
          <div className="max-w-7xl mx-auto px-6">
            <UrgentNeeds />
          </div>
        </section>

        {/* Role Value Props Section - Pure White Background */}
        <section className="py-24 bg-white dark:bg-slate-950">
          <div className="max-w-7xl mx-auto px-6">
            <div className="text-center mb-16 max-w-3xl mx-auto">
              <h2 className="text-3xl md:text-5xl font-bold mb-6 text-slate-900 dark:text-white tracking-tight">
                A Platform for Every Hero
              </h2>
              <p className="text-lg md:text-xl text-slate-600 dark:text-slate-400 font-medium leading-relaxed">
                Whether you are seeking aid or providing it, our architecture adapts to your needs with precision and speed.
              </p>
            </div>

            <RoleCards />
          </div>
        </section>

        {/* Stories Section */}
        <section className="py-24 px-6 bg-slate-50 dark:bg-slate-900">
          <div className="max-w-7xl mx-auto">
            <div className="flex flex-col md:flex-row md:items-end justify-between mb-12 gap-6">
              <div>
                <h2 className="text-3xl md:text-4xl font-bold text-slate-900 dark:text-white mb-3">Voices from the Field</h2>
                <p className="text-lg text-slate-600 dark:text-slate-400 font-medium">Real stories from real crises, verified by our network.</p>
              </div>
              <div className="flex gap-2">
                <div className="px-4 py-1.5 rounded-full border border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-400 text-xs font-bold uppercase tracking-wider">
                  Verified Impact
                </div>
              </div>
            </div>
            <SuccessStories />
          </div>
        </section>

        {/* CTA Footer */}
        <section className="py-24 px-6 relative overflow-hidden bg-blue-600 dark:bg-slate-950 text-white">
          <div className="absolute inset-0 z-0">
            {/* Decorative background for footer */}
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_var(--tw-gradient-stops))] from-blue-500 via-blue-600 to-blue-700 dark:from-slate-800 dark:via-slate-900 dark:to-slate-950 opacity-100" />
          </div>

          <div className="max-w-4xl mx-auto text-center relative z-10">
            <h2 className="text-4xl md:text-6xl font-bold mb-8 tracking-tight text-white">Ready to Make a Difference?</h2>
            <p className="text-xl text-blue-100 dark:text-slate-300 mb-12 leading-relaxed max-w-2xl mx-auto font-medium">
              Join the network that turns empathy into action. Every second counts.
            </p>
            <Link
              href="/signup"
              className="inline-flex items-center gap-2 bg-white text-blue-600 dark:text-slate-900 hover:bg-slate-50 px-10 py-5 rounded-full font-bold text-xl transition-all hover:scale-105 shadow-2xl shadow-blue-900/20"
            >
              Get Started Now
              <Activity className="w-6 h-6 text-blue-600 dark:text-slate-900" />
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 py-16">
        <div className="max-w-7xl mx-auto px-6 grid grid-cols-1 md:grid-cols-4 gap-12 mb-12">
          <div className="col-span-1 md:col-span-2">
            <div className="flex items-center gap-2 font-bold text-2xl text-slate-900 dark:text-white mb-6">
              <Activity className="text-blue-600 dark:text-blue-500" />
              <span>HopeInChaos</span>
            </div>
            <p className="text-slate-600 dark:text-slate-400 max-w-sm text-lg leading-relaxed">
              Open source disaster relief coordination platform built for resilience, transparency, and speed.
            </p>
          </div>
          <div>
            <h4 className="text-slate-900 dark:text-white font-bold mb-6 text-lg">Platform</h4>
            <ul className="space-y-4 text-slate-600 dark:text-slate-500 font-medium">
              <li><a href="#" className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Live Map</a></li>
              <li><a href="#" className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Volunteer</a></li>
              <li><a href="#" className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Donate</a></li>
            </ul>
          </div>
          <div>
            <h4 className="text-slate-900 dark:text-white font-bold mb-6 text-lg">Legal</h4>
            <ul className="space-y-4 text-slate-600 dark:text-slate-500 font-medium">
              <li><a href="#" className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Privacy Policy</a></li>
              <li><a href="#" className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Terms of Service</a></li>
            </ul>
          </div>
        </div>
        <div className="text-center text-slate-500 dark:text-slate-600 text-sm border-t border-slate-100 dark:border-slate-900 pt-8">
          <p>&copy; {new Date().getFullYear()} Disaster Relief Coordination Platform.</p>
        </div>
      </footer>
    </div>
  );
}
