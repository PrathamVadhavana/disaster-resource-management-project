import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Loader2, User, Users, Calendar, MapPin } from 'lucide-react'
import toast from 'react-hot-toast'

interface ReassignmentModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  requestId: string
  currentAssignedTo?: string
}

interface User {
  id: string
  name: string
  email: string
  role: string
  location?: string
}

export function ReassignmentModal({ isOpen, onClose, onSuccess, requestId, currentAssignedTo }: ReassignmentModalProps) {
  const [formData, setFormData] = useState({
    assigned_to: currentAssignedTo || '',
    reason: '',
    notes: '',
  })
  
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const queryClient = useQueryClient()

  // Fetch available users for reassignment
  const { data: users, isLoading: loadingUsers } = useQuery({
    queryKey: ['users-for-reassignment'],
    queryFn: () => api.getUsers(),
    enabled: isOpen,
    retry: false,
  })

  const reassignMutation = useMutation({
    mutationFn: (data: { assigned_to: string; reason: string; notes: string }) => 
      api.adminRequestAction(requestId, {
        action: 'reassign',
        assigned_to: data.assigned_to,
        admin_note: data.notes,
        rejection_reason: data.reason,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sla-violations'] })
      queryClient.invalidateQueries({ queryKey: ['admin-requests'] })
      onSuccess()
      onClose()
      toast.success('Request reassigned successfully')
    },
    onError: (err: any) => {
      setError(err.message || 'Failed to reassign request')
      toast.error(err.message || 'Failed to reassign request')
    },
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)

    if (!formData.assigned_to) {
      setError('Please select a user to assign this request to')
      setIsSubmitting(false)
      return
    }

    try {
      await reassignMutation.mutateAsync(formData)
    } catch (err) {
      // Error is handled by onError
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!isOpen) return null

  const availableUsers = Array.isArray(users) ? users : []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
              <Users className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">Reassign Request</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">Transfer this request to another team member</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors"
            disabled={isSubmitting}
          >
            <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20">
            <p className="text-xs text-red-600 dark:text-red-400 font-medium">{error}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="assigned_to">Assign To</Label>
            <Select
              value={formData.assigned_to}
              onChange={(e) => setFormData({ ...formData, assigned_to: e.target.value })}
              disabled={loadingUsers || isSubmitting}
              className="w-full"
            >
              <option value="">{loadingUsers ? "Loading users..." : "Select team member"}</option>
              {availableUsers.map((user: User) => (
                <option key={user.id} value={user.id}>
                  {user.name} ({user.role})
                </option>
              ))}
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="reason">Reassignment Reason</Label>
            <Textarea
              id="reason"
              value={formData.reason}
              onChange={(e) => setFormData({ ...formData, reason: e.target.value })}
              placeholder="Why is this request being reassigned? (e.g., workload balance, expertise match, availability)"
              rows={3}
              required
              disabled={isSubmitting}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="notes">Additional Notes</Label>
            <Textarea
              id="notes"
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              placeholder="Any additional context for the new assignee..."
              rows={2}
              disabled={isSubmitting}
            />
          </div>

          <div className="flex gap-3 pt-2">
            <Button type="submit" disabled={isSubmitting || loadingUsers} className="flex-1">
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Reassigning...
                </>
              ) : (
                'Reassign Request'
              )}
            </Button>
            <Button type="button" variant="outline" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}