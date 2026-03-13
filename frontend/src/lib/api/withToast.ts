import { api } from './index'
import { showToast } from '../toast'

// Helper to get entity name from API call for toast messages
const getEntityName = (apiCall: string): string => {
  const entityMap: { [key: string]: string } = {
    'createDisaster': 'Disaster',
    'updateDisaster': 'Disaster',
    'deleteDisaster': 'Disaster',
    'createResource': 'Resource',
    'updateResource': 'Resource',
    'deleteResource': 'Resource',
    'createCertification': 'Certification',
    'updateCertification': 'Certification',
    'deleteCertification': 'Certification',
    'createDonation': 'Donation',
    'updateDonation': 'Donation',
    'deleteDonation': 'Donation',
    'createPledge': 'Pledge',
    'removePledge': 'Pledge',
    'createSourcingRequest': 'Sourcing Request',
    'createMobilization': 'Mobilization',
    'adoptRequest': 'Request Adoption',
    'verifyRequest': 'Request Verification',
    'completeAssignment': 'Assignment Completion',
    'confirmUserVerification': 'User Verification',
    'addNgoInventoryItem': 'Inventory Item',
    'updateNgoInventoryItem': 'Inventory Item',
    'submitNgoAvailability': 'NGO Availability',
    'updateNgoDeliveryStatus': 'Delivery Status',
    'updateVolunteerProfile': 'Volunteer Profile',
    'updateMyProfile': 'Profile',
    'switchRole': 'Role Switch',
    'postDisasterChat': 'Chat Message',
    'adminRequestAction': 'Request Action',
    'adminUpdateRequestStatus': 'Request Status',
    'markAdminNotificationsRead': 'Notifications',
    'markNgoNotificationsRead': 'Notifications',
    'markNotificationsRead': 'Notifications',
    'scheduleSitrep': 'Situation Report',
    'generateSitrep': 'Situation Report',
    'runAnomalyDetection': 'Anomaly Detection',
    'acknowledgeAnomaly': 'Anomaly Acknowledgment',
    'resolveAnomaly': 'Anomaly Resolution',
    'autoCaptureOutcomes': 'Outcome Capture',
    'generateEvaluationReport': 'Evaluation Report',
    'trainRL': 'RL Training',
    'trainFederated': 'Federated Training',
    'startOrchestrator': 'Orchestrator',
    'stopOrchestrator': 'Orchestrator',
    'triggerLLMIndex': 'LLM Index',
    'applyFairnessPlan': 'Fairness Plan',
    'getCausalAudit': 'Causal Audit',
    'runCounterfactual': 'Counterfactual Analysis',
    'rlAllocate': 'RL Allocation',
    'gatMatch': 'GAT Matching',
    'runFederatedRound': 'Federated Round',
    'agentQuery': 'Agent Query',
    'pinnPredict': 'PINN Prediction',
    'pinnPredictGrid': 'PINN Grid Prediction',
  }
  
  return entityMap[apiCall] || 'Operation'
}

// Generic wrapper for API calls with toast notifications
export const withToast = async <T>(
  apiCall: Promise<T>,
  operationName: string,
  entityName?: string
): Promise<T> => {
  const entity = entityName || getEntityName(operationName)
  
  try {
    const loadingToast = showToast.processLoading(operationName)
    const result = await apiCall
    showToast.success(`${entity} completed successfully`)
    return result
  } catch (error: any) {
    console.error(`${operationName} failed:`, error)
    
    if (error.status === 401) {
      showToast.error('Authentication required. Please log in again.')
    } else if (error.status === 403) {
      showToast.error('You do not have permission to perform this action.')
    } else if (error.status === 404) {
      showToast.error(`${entity} not found.`)
    } else if (error.status === 409) {
      showToast.error(`${entity} already exists or is in use.`)
    } else if (error.status === 422) {
      showToast.error('Invalid input. Please check your data and try again.')
    } else if (error.status >= 500) {
      showToast.error('Server error. Please try again later.')
    } else {
      showToast.error(`${entity} failed: ${error.message || 'Unknown error'}`)
    }
    throw error
  }
}

// Specific wrappers for common operations
export const apiWithToast = {
  // Disasters
  createDisaster: (data: any) => withToast(api.createDisaster(data), 'createDisaster'),
  updateDisaster: (id: string, data: any) => withToast(api.updateDisaster(id, data), 'updateDisaster'),
  deleteDisaster: (id: string) => withToast(api.deleteDisaster(id), 'deleteDisaster'),
  
  // Resources
  createResource: (data: any) => withToast(api.createResource(data), 'createResource'),
  updateResource: (resourceId: string, data: any) => withToast(api.updateResource(resourceId, data), 'updateResource'),
  deleteResource: (resourceId: string) => withToast(api.deleteResource(resourceId), 'deleteResource'),
  
  // Certifications
  createCertification: (data: any) => withToast(api.createCertification(data), 'createCertification'),
  updateCertification: (id: string, data: any) => withToast(api.updateCertification(id, data), 'updateCertification'),
  deleteCertification: (id: string) => withToast(api.deleteCertification(id), 'deleteCertification'),
  
  // Donations
  createDonation: (data: any) => withToast(api.createDonation(data), 'createDonation'),
  updateDonation: (id: string, data: any) => withToast(api.updateDonation(id, data), 'updateDonation'),
  deleteDonation: (id: string) => withToast(api.deleteDonation(id), 'deleteDonation'),
  
  // Pledges
  createPledge: (disasterId: string) => withToast(api.createPledge(disasterId), 'createPledge'),
  removePledge: (disasterId: string) => withToast(api.removePledge(disasterId), 'removePledge'),
  
  // Interactivity
  createSourcingRequest: (data: any) => withToast(api.createSourcingRequest(data), 'createSourcingRequest'),
  createMobilization: (data: any) => withToast(api.createMobilization(data), 'createMobilization'),
  adoptRequest: (requestId: string) => withToast(api.adoptRequest(requestId), 'adoptRequest'),
  verifyRequest: (data: any) => withToast(api.verifyRequest(data), 'verifyRequest'),
  completeAssignment: (assignmentId: string, feedback: string = '') => withToast(api.completeAssignment(assignmentId, feedback), 'completeAssignment'),
  
  // Admin
  confirmUserVerification: (userId: string, status: string, notes?: string) => 
    withToast(api.confirmUserVerification(userId, status, notes), 'confirmUserVerification'),
  
  // NGO
  addNgoInventoryItem: (data: any) => withToast(api.addNgoInventoryItem(data), 'addNgoInventoryItem'),
  updateNgoInventoryItem: (resourceId: string, params: any) => withToast(api.updateNgoInventoryItem(resourceId, params), 'updateNgoInventoryItem'),
  submitNgoAvailability: (requestId: string, data: any) => withToast(api.submitNgoAvailability(requestId, data), 'submitNgoAvailability'),
  updateNgoDeliveryStatus: (requestId: string, data: any) => withToast(api.updateNgoDeliveryStatus(requestId, data), 'updateNgoDeliveryStatus'),
  
  // Profile
  updateVolunteerProfile: (data: any) => withToast(api.updateVolunteerProfile(data), 'updateVolunteerProfile'),
  updateMyProfile: (data: any) => withToast(api.updateMyProfile(data), 'updateMyProfile'),
  switchRole: (newRole: string) => withToast(api.switchRole(newRole), 'switchRole'),
  
  // Chat
  postDisasterChat: (disasterId: string, data: any) => withToast(api.postDisasterChat(disasterId, data), 'postDisasterChat'),
  
  // Admin Actions
  adminRequestAction: (requestId: string, data: any) => withToast(api.adminRequestAction(requestId, data), 'adminRequestAction'),
  adminUpdateRequestStatus: (requestId: string, data: any) => withToast(api.adminUpdateRequestStatus(requestId, data), 'adminUpdateRequestStatus'),
  
  // Notifications
  markAdminNotificationsRead: (notificationIds?: string[]) => withToast(api.markAdminNotificationsRead(notificationIds), 'markAdminNotificationsRead'),
  markNgoNotificationsRead: (notificationIds?: string[]) => withToast(api.markNgoNotificationsRead(notificationIds), 'markNgoNotificationsRead'),
  markNotificationsRead: (notificationIds?: string[]) => withToast(api.markNotificationsRead(notificationIds), 'markNotificationsRead'),
  
  // Reports
  scheduleSitrep: (data: any) => withToast(api.scheduleSitrep(data), 'scheduleSitrep'),
  generateSitrep: (reportType: string = 'on_demand', generatedBy: string = 'user') => 
    withToast(api.generateSitrep(reportType, generatedBy), 'generateSitrep'),
  
  // ML Operations
  runAnomalyDetection: () => withToast(api.runAnomalyDetection(), 'runAnomalyDetection'),
  acknowledgeAnomaly: (alertId: string, userId: string) => withToast(api.acknowledgeAnomaly(alertId, userId), 'acknowledgeAnomaly'),
  resolveAnomaly: (alertId: string, status: string = 'resolved') => withToast(api.resolveAnomaly(alertId, status), 'resolveAnomaly'),
  autoCaptureOutcomes: () => withToast(api.autoCaptureOutcomes(), 'autoCaptureOutcomes'),
  generateEvaluationReport: (params?: any) => withToast(api.generateEvaluationReport(params), 'generateEvaluationReport'),
  trainRL: (nEpisodes: number = 500) => withToast(api.trainRL(nEpisodes), 'trainRL'),
  trainFederated: (data?: any) => withToast(api.trainFederated(data), 'trainFederated'),
  startOrchestrator: () => withToast(api.startOrchestrator(), 'startOrchestrator'),
  stopOrchestrator: () => withToast(api.stopOrchestrator(), 'stopOrchestrator'),
  triggerLLMIndex: () => withToast(api.triggerLLMIndex(), 'triggerLLMIndex'),
  applyFairnessPlan: (data: any) => withToast(api.applyFairnessPlan(data), 'applyFairnessPlan'),
  getCausalAudit: (disasterId: string) => withToast(api.getCausalAudit(disasterId), 'getCausalAudit'),
  runCounterfactual: (data: any) => withToast(api.runCounterfactual(data), 'runCounterfactual'),
  rlAllocate: (data: any) => withToast(api.rlAllocate(data), 'rlAllocate'),
  gatMatch: (data?: any) => withToast(api.gatMatch(data), 'gatMatch'),
  runFederatedRound: (data?: any) => withToast(api.runFederatedRound(data), 'runFederatedRound'),
  agentQuery: (data: any) => withToast(api.agentQuery(data), 'agentQuery'),
  pinnPredict: (data: any) => withToast(api.pinnPredict(data), 'pinnPredict'),
  pinnPredictGrid: (data: any) => withToast(api.pinnPredictGrid(data), 'pinnPredictGrid'),
  
  // Fallback for any API call
  call: <T>(apiCall: Promise<T>, operationName: string, entityName?: string) => 
    withToast(apiCall, operationName, entityName),
}