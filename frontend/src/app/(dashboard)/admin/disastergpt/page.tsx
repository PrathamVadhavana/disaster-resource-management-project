import { DisasterGPT } from '@/components/coordinator/DisasterGPT'

export default function DisasterGPTPage() {
    return (
        <div className="h-[calc(100vh-180px)]">
            <DisasterGPT embedded />
        </div>
    )
}
