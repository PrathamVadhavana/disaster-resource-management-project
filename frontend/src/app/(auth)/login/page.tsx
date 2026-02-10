import AuthForm from '@/components/auth/AuthForm';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';

// Define props for the page
interface LoginPageProps {
    searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
    const params = await searchParams;
    const initialView = params.view === 'signup' ? 'signup' : 'login';

    return (
        <div className="min-h-screen bg-white dark:bg-slate-950 flex flex-col items-center justify-center p-4 relative overflow-hidden">
            {/* Dynamic Background */}
            <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none">
                <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-500/10 dark:bg-blue-600/20 rounded-full blur-[120px]" />
                <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-emerald-500/10 dark:bg-emerald-500/10 rounded-full blur-[120px]" />
            </div>

            <div className="w-full max-w-md relative z-10">
                <Link href="/" className="inline-flex items-center text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white mb-8 transition-colors">
                    <ArrowLeft className="w-4 h-4 mr-2" />
                    Back to Home
                </Link>

                <div className="text-center mb-8">
                    <h1 className="text-4xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-emerald-600 dark:from-blue-400 dark:to-emerald-400 mb-2">
                        Hope in Chaos
                    </h1>
                    <p className="text-slate-600 dark:text-slate-400 font-medium">Disaster Relief Coordination Platform</p>
                </div>

                <AuthForm initialView={initialView as 'login' | 'signup'} />
            </div>
        </div>
    );
}
