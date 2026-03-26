import { VolunteerSidebar } from '@/components/volunteer/Sidebar'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { VerificationBanner } from '@/components/shared/VerificationBanner'
import { NotificationBell } from '@/components/shared/NotificationBell'

export default function VolunteerLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className="flex min-h-screen bg-slate-50 dark:bg-slate-950">
            <VolunteerSidebar />
            <main className="flex-1 lg:ml-0">
                <div className="fixed top-3 right-3 lg:top-5 lg:right-6 z-50">
                    <NotificationBell />
                </div>
                <div className="pt-20 lg:pt-8 pb-8 px-4 sm:px-6 lg:px-8 max-w-5xl mx-auto">
                    <VerificationBanner />
                    <ErrorBoundary>{children}</ErrorBoundary>
                </div>
            </main>
        </div>
    )
}
