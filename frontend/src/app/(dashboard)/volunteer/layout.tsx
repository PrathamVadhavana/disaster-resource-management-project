import { VolunteerSidebar } from '@/components/volunteer/Sidebar'
import { ErrorBoundary } from '@/components/ErrorBoundary'

export default function VolunteerLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className="flex min-h-screen bg-slate-50 dark:bg-slate-950">
            <VolunteerSidebar />
            <main className="flex-1 lg:ml-0">
                <div className="pt-20 lg:pt-8 pb-8 px-4 sm:px-6 lg:px-8 max-w-5xl mx-auto">
                    <ErrorBoundary>{children}</ErrorBoundary>
                </div>
            </main>
        </div>
    )
}
