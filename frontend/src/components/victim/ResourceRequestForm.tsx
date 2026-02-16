'use client'

import { useState, useCallback, useMemo, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
    createResourceRequest, updateResourceRequest, getAvailableResources,
    type ResourceRequest, type ResourceItem, type RequestPriority, type AvailableResource,
} from '@/lib/api/victim'
import { cn } from '@/lib/utils'
import {
    ArrowLeft, MapPin, Loader2, Plus, Trash2, ChevronDown, Package, AlertCircle,
} from 'lucide-react'
import Link from 'next/link'

// ─── Constants ──────────────────────────────────────────
const PRIORITIES: { value: RequestPriority; label: string; color: string; darkColor: string }[] = [
    { value: 'critical', label: 'Critical', color: 'border-red-300 bg-red-50 text-red-700', darkColor: 'dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400' },
    { value: 'high', label: 'High', color: 'border-orange-300 bg-orange-50 text-orange-700', darkColor: 'dark:border-orange-500/30 dark:bg-orange-500/10 dark:text-orange-400' },
    { value: 'medium', label: 'Medium', color: 'border-yellow-300 bg-yellow-50 text-yellow-700', darkColor: 'dark:border-yellow-500/30 dark:bg-yellow-500/10 dark:text-yellow-400' },
    { value: 'low', label: 'Low', color: 'border-slate-300 bg-slate-50 text-slate-600', darkColor: 'dark:border-slate-500/30 dark:bg-slate-500/10 dark:text-slate-400' },
]

const CATEGORY_EMOJI: Record<string, string> = {
    Food: '🍞', Medical: '🏥', Shelter: '🏠', Clothes: '👕',
    Water: '💧', Volunteers: '🙋', Custom: '📦',
}

interface FormItem {
    id: string
    resource_type: string
    quantity: number
    custom_name: string
    // Linked available resource info
    available_resource_id?: string
    max_quantity?: number
    unit?: string
}

function generateId() {
    return Math.random().toString(36).slice(2, 9)
}

export function ResourceRequestForm({ editRequest }: { editRequest?: ResourceRequest }) {
    const router = useRouter()
    const queryClient = useQueryClient()
    const isEdit = !!editRequest

    // Fetch available resources from DB
    const { data: availableData, isLoading: loadingResources } = useQuery({
        queryKey: ['available-resources'],
        queryFn: () => getAvailableResources(),
        staleTime: 30_000,
    })
    const availableResources = availableData?.resources || []

    // Group by category for display
    const resourcesByCategory = useMemo(() => {
        const grouped: Record<string, AvailableResource[]> = {}
        for (const r of availableResources) {
            if (!grouped[r.category]) grouped[r.category] = []
            grouped[r.category].push(r)
        }
        return grouped
    }, [availableResources])

    // Items state
    // Items state - start empty to match server, populate on client mount
    const [items, setItems] = useState<FormItem[]>([])

    useEffect(() => {
        if (editRequest?.items?.length) {
            setItems(editRequest.items.map((it) => ({
                id: generateId(),
                resource_type: it.resource_type,
                quantity: it.quantity,
                custom_name: it.custom_name || '',
            })))
        } else if (items.length === 0) {
            setItems([{ id: generateId(), resource_type: '', quantity: 1, custom_name: '' }])
        }
    }, [editRequest])

    const [priority, setPriority] = useState<RequestPriority>(
        (editRequest?.priority as RequestPriority) || 'medium'
    )
    const [description, setDescription] = useState(editRequest?.description || '')
    const [addressText, setAddressText] = useState(editRequest?.address_text || '')
    const [latitude, setLatitude] = useState<number | null>(editRequest?.latitude ?? null)
    const [longitude, setLongitude] = useState<number | null>(editRequest?.longitude ?? null)
    const [locating, setLocating] = useState(false)
    const [error, setError] = useState('')

    // Add / remove items
    const addItem = useCallback(() => {
        setItems((prev) => [...prev, { id: generateId(), resource_type: '', quantity: 1, custom_name: '' }])
    }, [])

    const removeItem = useCallback((id: string) => {
        setItems((prev) => (prev.length > 1 ? prev.filter((i) => i.id !== id) : prev))
    }, [])

    const updateItem = useCallback((id: string, field: keyof FormItem, value: string | number) => {
        setItems((prev) => prev.map((i) => {
            if (i.id !== id) return i
            const updated = { ...i, [field]: value }
            // When selecting a resource, link the available resource info
            if (field === 'resource_type' && typeof value === 'string') {
                const ar = availableResources.find((r) => r.title === value || r.resource_type === value)
                if (ar) {
                    updated.available_resource_id = ar.resource_id
                    updated.max_quantity = ar.remaining_quantity
                    updated.unit = ar.unit
                    if (updated.quantity > ar.remaining_quantity) {
                        updated.quantity = ar.remaining_quantity
                    }
                } else {
                    updated.available_resource_id = undefined
                    updated.max_quantity = undefined
                    updated.unit = undefined
                }
            }
            return updated
        }))
    }, [availableResources])

    // GPS detection
    const detectLocation = () => {
        if (!navigator.geolocation) return
        setLocating(true)
        navigator.geolocation.getCurrentPosition(
            async (pos) => {
                setLatitude(pos.coords.latitude)
                setLongitude(pos.coords.longitude)
                try {
                    const res = await fetch(
                        `https://nominatim.openstreetmap.org/reverse?lat=${pos.coords.latitude}&lon=${pos.coords.longitude}&format=json`
                    )
                    const data = await res.json()
                    if (data.display_name) setAddressText(data.display_name)
                } catch { /* ignore */ }
                setLocating(false)
            },
            () => setLocating(false),
            { enableHighAccuracy: true }
        )
    }

    // Mutations
    const createMut = useMutation({
        mutationFn: createResourceRequest,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['victim-requests'] })
            queryClient.invalidateQueries({ queryKey: ['victim-stats'] })
            router.push('/victim/requests')
        },
    })

    const updateMut = useMutation({
        mutationFn: (data: Parameters<typeof updateResourceRequest>[1]) =>
            updateResourceRequest(editRequest!.id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['victim-requests'] })
            queryClient.invalidateQueries({ queryKey: ['victim-request', editRequest!.id] })
            router.push(`/victim/requests/${editRequest!.id}`)
        },
    })

    const submitting = createMut.isPending || updateMut.isPending

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        setError('')

        const validItems = items.filter((i) => i.resource_type)
        if (validItems.length === 0) {
            setError('Please add at least one resource item.')
            return
        }
        for (const it of validItems) {
            if (it.resource_type === 'Custom' && !it.custom_name.trim()) {
                setError('Please provide a name for each custom resource.')
                return
            }
            if (it.quantity < 1) {
                setError('Quantity must be at least 1.')
                return
            }
            if (it.max_quantity && it.quantity > it.max_quantity) {
                setError(`Quantity for "${it.resource_type}" exceeds available stock (${it.max_quantity}).`)
                return
            }
        }

        const itemsPayload: ResourceItem[] = validItems.map((i) => ({
            resource_type: i.resource_type,
            quantity: i.quantity,
            custom_name: i.resource_type === 'Custom' ? i.custom_name : undefined,
        }))

        const payload = {
            items: itemsPayload,
            priority,
            description: description || undefined,
            latitude: latitude ?? undefined,
            longitude: longitude ?? undefined,
            address_text: addressText || undefined,
        }

        if (isEdit) {
            updateMut.mutate(payload)
        } else {
            createMut.mutate(payload)
        }
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center gap-3">
                <Link
                    href={isEdit ? `/victim/requests/${editRequest!.id}` : '/victim/requests'}
                    className="p-2 rounded-xl bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 hover:bg-slate-50 dark:hover:bg-white/10 transition-colors"
                >
                    <ArrowLeft className="w-4 h-4 text-slate-600 dark:text-slate-400" />
                </Link>
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
                        {isEdit ? 'Edit Request' : 'New Resource Request'}
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400">
                        {isEdit ? 'Update your pending request' : 'Select from available resources or add custom ones'}
                    </p>
                </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
                {/* ── Resource Items ─────────────────────────── */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
                        <div>
                            <h2 className="font-semibold text-slate-900 dark:text-white">Resources Needed</h2>
                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                                Pick from available stock or request custom resources
                            </p>
                        </div>
                        <button
                            type="button"
                            onClick={addItem}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 text-sm font-medium hover:bg-red-100 dark:hover:bg-red-500/20 transition-colors"
                        >
                            <Plus className="w-4 h-4" />
                            Add Resource
                        </button>
                    </div>

                    <div className="p-5 space-y-4">
                        {loadingResources && (
                            <div className="flex items-center gap-2 text-sm text-slate-400 py-4 justify-center">
                                <Loader2 className="w-4 h-4 animate-spin" />
                                Loading available resources…
                            </div>
                        )}

                        {items.length === 0 && (
                            <div className="flex justify-center py-8">
                                <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
                            </div>
                        )}

                        {items.map((item) => {
                            const linkedResource = item.available_resource_id
                                ? availableResources.find((r) => r.resource_id === item.available_resource_id)
                                : null

                            return (
                                <div key={item.id} className="flex flex-col gap-3 p-4 rounded-xl bg-slate-50 dark:bg-white/[0.03] border border-slate-100 dark:border-white/5">
                                    <div className="flex flex-col sm:flex-row gap-3">
                                        {/* Resource selector */}
                                        <div className="flex-1">
                                            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">
                                                Resource
                                            </label>
                                            <div className="relative">
                                                <select
                                                    value={item.resource_type}
                                                    onChange={(e) => updateItem(item.id, 'resource_type', e.target.value)}
                                                    className="w-full appearance-none pl-3 pr-8 py-2.5 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-red-500/30 focus:border-red-500/50"
                                                >
                                                    <option value="">Select resource…</option>

                                                    {/* DB available resources grouped by category */}
                                                    {Object.entries(resourcesByCategory).map(([category, resources]) => (
                                                        <optgroup key={category} label={`${CATEGORY_EMOJI[category] || '📦'} ${category}`}>
                                                            {resources.map((r) => (
                                                                <option key={r.resource_id} value={r.title}>
                                                                    {r.title} — {r.remaining_quantity} {r.unit} available
                                                                </option>
                                                            ))}
                                                        </optgroup>
                                                    ))}

                                                    {/* Always allow custom + volunteers */}
                                                    <optgroup label="🙋 Other">
                                                        <option value="Volunteers">🙋 Volunteers</option>
                                                        <option value="Custom">📦 Custom Resource</option>
                                                    </optgroup>
                                                </select>
                                                <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                                            </div>
                                        </div>

                                        {/* Custom name */}
                                        {item.resource_type === 'Custom' && (
                                            <div className="flex-1">
                                                <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">
                                                    Custom Resource Name
                                                </label>
                                                <input
                                                    type="text"
                                                    value={item.custom_name}
                                                    onChange={(e) => updateItem(item.id, 'custom_name', e.target.value)}
                                                    placeholder="e.g. Baby formula, Wheelchair…"
                                                    className="w-full px-3 py-2.5 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-red-500/30 focus:border-red-500/50"
                                                />
                                            </div>
                                        )}

                                        {/* Quantity */}
                                        <div className="w-full sm:w-28">
                                            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">
                                                Qty
                                            </label>
                                            <input
                                                type="number"
                                                min={1}
                                                max={item.max_quantity || undefined}
                                                value={item.quantity}
                                                onChange={(e) => updateItem(item.id, 'quantity', Math.max(1, parseInt(e.target.value) || 1))}
                                                className="w-full px-3 py-2.5 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-red-500/30 focus:border-red-500/50"
                                            />
                                        </div>

                                        {/* Remove */}
                                        {items.length > 1 && (
                                            <button
                                                type="button"
                                                onClick={() => removeItem(item.id)}
                                                className="self-end sm:self-center p-2 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        )}
                                    </div>

                                    {/* Available stock info badge */}
                                    {linkedResource && (
                                        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 text-xs">
                                            <Package className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                                            <span className="text-emerald-700 dark:text-emerald-400 font-medium">
                                                {linkedResource.remaining_quantity} {linkedResource.unit} available
                                            </span>
                                            <span className="text-emerald-500 dark:text-emerald-500/80">
                                                ({linkedResource.category} · {linkedResource.resource_type})
                                            </span>
                                            {linkedResource.address_text && (
                                                <span className="text-emerald-500 dark:text-emerald-500/70 ml-auto truncate max-w-[180px]">
                                                    📍 {linkedResource.address_text}
                                                </span>
                                            )}
                                        </div>
                                    )}

                                    {/* Over-request warning */}
                                    {item.max_quantity && item.quantity > item.max_quantity && (
                                        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 text-xs">
                                            <AlertCircle className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                                            <span className="text-amber-700 dark:text-amber-400">
                                                Exceeds available stock ({item.max_quantity} {item.unit || 'units'} available)
                                            </span>
                                        </div>
                                    )}
                                </div>
                            )
                        })}

                        {!loadingResources && availableResources.length === 0 && (
                            <div className="text-center py-4 text-sm text-slate-400 dark:text-slate-500">
                                No resources currently available in stock. You can still request custom resources or volunteers.
                            </div>
                        )}
                    </div>
                </div>

                {/* ── Priority ───────────────────────────────── */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5">
                        <h2 className="font-semibold text-slate-900 dark:text-white">Priority Level</h2>
                    </div>
                    <div className="p-5 grid grid-cols-2 sm:grid-cols-4 gap-3">
                        {PRIORITIES.map((p) => (
                            <button
                                key={p.value}
                                type="button"
                                onClick={() => setPriority(p.value)}
                                className={cn(
                                    'px-4 py-3 rounded-xl border-2 text-sm font-semibold transition-all',
                                    priority === p.value
                                        ? cn(p.color, p.darkColor, 'ring-2 ring-offset-1 ring-offset-white dark:ring-offset-slate-950')
                                        : 'border-slate-200 dark:border-white/10 text-slate-500 dark:text-slate-400 hover:border-slate-300 dark:hover:border-white/20'
                                )}
                            >
                                {p.label}
                            </button>
                        ))}
                    </div>
                </div>

                {/* ── Additional Info ────────────────────────── */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5">
                        <h2 className="font-semibold text-slate-900 dark:text-white">Additional Details</h2>
                    </div>
                    <div className="p-5 space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                                Description <span className="text-slate-400">(optional)</span>
                            </label>
                            <textarea
                                value={description}
                                onChange={(e) => setDescription(e.target.value)}
                                rows={3}
                                placeholder="Describe your situation or any specific requirements…"
                                className="w-full px-4 py-3 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-red-500/30 focus:border-red-500/50 resize-none"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                                Location
                            </label>
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    value={addressText}
                                    onChange={(e) => setAddressText(e.target.value)}
                                    placeholder="Address or location description"
                                    className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-red-500/30 focus:border-red-500/50"
                                />
                                <button
                                    type="button"
                                    onClick={detectLocation}
                                    disabled={locating}
                                    className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-100 dark:bg-white/5 border border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-300 text-sm font-medium hover:bg-slate-200 dark:hover:bg-white/10 transition-colors disabled:opacity-50"
                                >
                                    {locating ? <Loader2 className="w-4 h-4 animate-spin" /> : <MapPin className="w-4 h-4" />}
                                    GPS
                                </button>
                            </div>
                            {latitude && longitude && (
                                <p className="text-xs text-slate-400 mt-1.5">
                                    📍 {latitude.toFixed(4)}, {longitude.toFixed(4)}
                                </p>
                            )}
                        </div>
                    </div>
                </div>

                {/* Error */}
                {(error || createMut.error || updateMut.error) && (
                    <div className="p-4 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-400 text-sm">
                        {error || createMut.error?.message || updateMut.error?.message}
                    </div>
                )}

                {/* Submit */}
                <button
                    type="submit"
                    disabled={submitting}
                    className="w-full py-3.5 rounded-xl bg-gradient-to-r from-red-500 to-orange-600 text-white font-semibold text-sm shadow-lg shadow-red-500/20 hover:shadow-red-500/30 hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                    {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
                    {isEdit ? 'Update Request' : 'Submit Request'}
                </button>
            </form>
        </div>
    )
}
