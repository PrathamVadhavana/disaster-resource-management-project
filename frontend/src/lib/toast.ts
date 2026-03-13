import { toast } from 'react-hot-toast'

export const toastMessages = {
  // Success messages
  createSuccess: (entity: string) => `${entity} created successfully`,
  updateSuccess: (entity: string) => `${entity} updated successfully`,
  deleteSuccess: (entity: string) => `${entity} deleted successfully`,
  assignSuccess: (entity: string) => `${entity} assigned successfully`,
  reassignSuccess: (entity: string) => `${entity} reassigned successfully`,
  approveSuccess: (entity: string) => `${entity} approved successfully`,
  rejectSuccess: (entity: string) => `${entity} rejected successfully`,
  fulfillSuccess: (entity: string) => `${entity} fulfilled successfully`,
  
  // Error messages
  createError: (entity: string) => `Failed to create ${entity}`,
  updateError: (entity: string) => `Failed to update ${entity}`,
  deleteError: (entity: string) => `Failed to delete ${entity}`,
  assignError: (entity: string) => `Failed to assign ${entity}`,
  reassignError: (entity: string) => `Failed to reassign ${entity}`,
  approveError: (entity: string) => `Failed to approve ${entity}`,
  rejectError: (entity: string) => `Failed to reject ${entity}`,
  fulfillError: (entity: string) => `Failed to fulfill ${entity}`,
  
  // Network errors
  networkError: 'Network error occurred. Please check your connection.',
  serverError: 'Server error occurred. Please try again later.',
  
  // Validation errors
  validationError: 'Please check your input and try again.',
  
  // Loading messages
  loading: (action: string) => `Processing ${action}...`,
}

export const showToast = {
  success: (message: string) => toast.success(message, {
    duration: 4000,
    position: 'top-right',
  }),
  
  error: (message: string) => toast.error(message, {
    duration: 5000,
    position: 'top-right',
  }),
  
  loading: (message: string) => toast.loading(message, {
    position: 'top-right',
  }),
  
  // Specific CRUD operations
  createSuccess: (entity: string) => showToast.success(toastMessages.createSuccess(entity)),
  updateSuccess: (entity: string) => showToast.success(toastMessages.updateSuccess(entity)),
  deleteSuccess: (entity: string) => showToast.success(toastMessages.deleteSuccess(entity)),
  assignSuccess: (entity: string) => showToast.success(toastMessages.assignSuccess(entity)),
  reassignSuccess: (entity: string) => showToast.success(toastMessages.reassignSuccess(entity)),
  approveSuccess: (entity: string) => showToast.success(toastMessages.approveSuccess(entity)),
  rejectSuccess: (entity: string) => showToast.success(toastMessages.rejectSuccess(entity)),
  fulfillSuccess: (entity: string) => showToast.success(toastMessages.fulfillSuccess(entity)),
  
  createError: (entity: string) => showToast.error(toastMessages.createError(entity)),
  updateError: (entity: string) => showToast.error(toastMessages.updateError(entity)),
  deleteError: (entity: string) => showToast.error(toastMessages.deleteError(entity)),
  assignError: (entity: string) => showToast.error(toastMessages.assignError(entity)),
  reassignError: (entity: string) => showToast.error(toastMessages.reassignError(entity)),
  approveError: (entity: string) => showToast.error(toastMessages.approveError(entity)),
  rejectError: (entity: string) => showToast.error(toastMessages.rejectError(entity)),
  fulfillError: (entity: string) => showToast.error(toastMessages.fulfillError(entity)),
  
  networkError: () => showToast.error(toastMessages.networkError),
  serverError: () => showToast.error(toastMessages.serverError),
  validationError: () => showToast.error(toastMessages.validationError),
  processLoading: (action: string) => showToast.loading(toastMessages.loading(action)),
}