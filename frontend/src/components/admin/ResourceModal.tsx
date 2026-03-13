import { useState } from 'react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Loader2, Package } from 'lucide-react'

interface ResourceModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  resourceToEdit?: any
}

const CATEGORIES = [
  'Food', 'Water', 'Medical', 'Shelter', 'Clothing', 'Financial Aid', 'Volunteers', 'Other'
]

const UNITS = [
  'units', 'kg', 'liters', 'packs', 'boxes', 'bottles', 'meals', 'beds', 'tents', 'sets'
]

export function ResourceModal({ isOpen, onClose, onSuccess, resourceToEdit }: ResourceModalProps) {
  const [formData, setFormData] = useState({
    title: resourceToEdit?.title || '',
    category: resourceToEdit?.category || 'Food',
    quantity: resourceToEdit?.total_quantity || 1,
    unit: resourceToEdit?.unit || 'units',
    description: resourceToEdit?.description || '',
  })
  
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      if (resourceToEdit) {
        // Update existing resource
        await api.updateResource(resourceToEdit.resource_id || resourceToEdit.id, {
          title: formData.title,
          category: formData.category,
          total_quantity: formData.quantity,
          unit: formData.unit,
          description: formData.description,
        })
      } else {
        // Create new resource
        await api.createResource({
          title: formData.title,
          category: formData.category,
          resource_type: formData.category,
          total_quantity: formData.quantity,
          unit: formData.unit,
          description: formData.description,
          status: 'available',
        })
      }
      
      onSuccess()
      onClose()
    } catch (err: any) {
      console.error('Resource save error:', err)
      // Handle FastAPI validation error arrays (which show up as [object Object] otherwise)
      const detail = err.detail || err.message
      if (Array.isArray(detail)) {
        setError(detail.map((d: any) => d.msg || d.message || JSON.stringify(d)).join(', '))
      } else if (typeof detail === 'object') {
        setError(JSON.stringify(detail))
      } else {
        setError(detail || 'Failed to save resource')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center">
              <Package className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                {resourceToEdit ? 'Edit Resource' : 'Add New Resource'}
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {resourceToEdit ? 'Update resource details' : 'Create a new resource'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors"
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
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="title">Resource Title</Label>
              <Input
                id="title"
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                placeholder="e.g., Bottled Water, Medical Kits"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="category">Category</Label>
              <Select
                value={formData.category}
                onChange={(e) => setFormData({ ...formData, category: e.target.value })}
              >
                {CATEGORIES.map((category) => (
                  <option key={category} value={category}>{category}</option>
                ))}
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="quantity">Quantity</Label>
              <Input
                id="quantity"
                type="number"
                min="1"
                value={formData.quantity}
                onChange={(e) => setFormData({ ...formData, quantity: parseInt(e.target.value) || 1 })}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="unit">Unit</Label>
              <Select
                value={formData.unit}
                onChange={(e) => setFormData({ ...formData, unit: e.target.value })}
              >
                {UNITS.map((unit) => (
                  <option key={unit} value={unit}>{unit}</option>
                ))}
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="Additional details about this resource..."
              rows={3}
            />
          </div>

          <div className="flex gap-3 pt-2">
            <Button type="submit" disabled={isSubmitting} className="flex-1">
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {resourceToEdit ? 'Updating...' : 'Creating...'}
                </>
              ) : (
                resourceToEdit ? 'Update Resource' : 'Create Resource'
              )}
            </Button>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}