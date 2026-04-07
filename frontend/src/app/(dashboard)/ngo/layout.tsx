import { NGOSidebar } from '@/components/ngo/Sidebar'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { VerificationBanner } from '@/components/shared/VerificationBanner'
import { NGOTopBar } from '@/components/ngo/TopBar'

export default function NGOLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className="flex min-h-screen bg-slate-50 dark:bg-slate-950">
            <NGOSidebar />
            <main className="flex-1 lg:ml-0">
                <NGOTopBar />
                <div className="pt-20 lg:pt-4 pb-8 px-4 sm:px-6 lg:px-8 max-w-5xl mx-auto">
                    <VerificationBanner />
                    <ErrorBoundary>{children}</ErrorBoundary>
                </div>
            </main>
        </div>
    )
}
