'use client'

import { RequestDetail } from '@/components/victim/RequestDetail'
import { useParams } from 'next/navigation'

export default function RequestDetailPage() {
    const params = useParams()
    const id = params.id as string

    return <RequestDetail requestId={id} />
}
