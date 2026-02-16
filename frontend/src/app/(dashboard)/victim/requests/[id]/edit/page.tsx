'use client'

import { useParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { getResourceRequest, type ResourceRequest } from '@/lib/api/victim'
import { ResourceRequestForm } from '@/components/victim/ResourceRequestForm'
import { Loader2 } from 'lucide-react'

export default function EditRequestPage() {
    const params = useParams()
    const id = params.id as string

    const { data: request, isLoading } = useQuery<ResourceRequest>({
        queryKey: ['victim-request', id],
        queryFn: () => getResourceRequest(id),
    })

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-slate-500 animate-spin" />
            </div>
        )
    }

    if (!request) {
        return (
            <div className="text-center text-slate-400 py-16">
                Request not found
            </div>
        )
    }

    return <ResourceRequestForm editRequest={request} />
}
