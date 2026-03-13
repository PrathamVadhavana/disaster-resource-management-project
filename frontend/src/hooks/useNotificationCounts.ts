import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { getSLAViolations } from '@/lib/api/workflow'

export interface NotificationCounts {
  slaViolations: number
  activeDisasters: number
  pendingRequests: number
}

export function useNotificationCounts() {
  const { data: slaData } = useQuery({
    queryKey: ['notification-counts', 'sla'],
    queryFn: async () => {
      try {
        const violations = await getSLAViolations()
        return violations?.violations?.length || 0
      } catch {
        return 0
      }
    },
    refetchInterval: 30000,
    staleTime: 30000,
  })

  const { data: disastersData } = useQuery({
    queryKey: ['notification-counts', 'disasters'],
    queryFn: async () => {
      try {
        const disasters = await api.getDisasters({ status: 'active' })
        return Array.isArray(disasters) ? disasters.length : 0
      } catch {
        return 0
      }
    },
    refetchInterval: 30000,
    staleTime: 30000,
  })

  const { data: requestsData } = useQuery({
    queryKey: ['notification-counts', 'requests'],
    queryFn: async () => {
      try {
        const requests = await api.getAdminRequests({ status: 'pending' })
        return Array.isArray(requests) ? requests.length : 0
      } catch {
        return 0
      }
    },
    refetchInterval: 30000,
    staleTime: 30000,
  })

  return {
    slaViolations: slaData || 0,
    activeDisasters: disastersData || 0,
    pendingRequests: requestsData || 0,
  }
}
