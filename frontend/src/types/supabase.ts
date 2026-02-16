export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export interface Database {
  public: {
    Tables: {
      disasters: {
        Row: {
          id: string
          created_at: string
          updated_at: string
          type: DisasterType
          severity: DisasterSeverity
          status: DisasterStatus
          title: string
          description: string | null
          location_id: string
          affected_population: number | null
          casualties: number | null
          estimated_damage: number | null
          start_date: string
          end_date: string | null
          metadata: Json | null
        }
        Insert: {
          id?: string
          created_at?: string
          updated_at?: string
          type: DisasterType
          severity: DisasterSeverity
          status?: DisasterStatus
          title: string
          description?: string | null
          location_id: string
          affected_population?: number | null
          casualties?: number | null
          estimated_damage?: number | null
          start_date: string
          end_date?: string | null
          metadata?: Json | null
        }
        Update: {
          id?: string
          created_at?: string
          updated_at?: string
          type?: DisasterType
          severity?: DisasterSeverity
          status?: DisasterStatus
          title?: string
          description?: string | null
          location_id?: string
          affected_population?: number | null
          casualties?: number | null
          estimated_damage?: number | null
          start_date?: string
          end_date?: string | null
          metadata?: Json | null
        }
      }
      locations: {
        Row: {
          id: string
          created_at: string
          name: string
          type: LocationType
          latitude: number
          longitude: number
          address: string | null
          city: string
          state: string
          country: string
          postal_code: string | null
          population: number | null
          area_sq_km: number | null
          metadata: Json | null
        }
        Insert: {
          id?: string
          created_at?: string
          name: string
          type: LocationType
          latitude: number
          longitude: number
          address?: string | null
          city: string
          state: string
          country: string
          postal_code?: string | null
          population?: number | null
          area_sq_km?: number | null
          metadata?: Json | null
        }
        Update: {
          id?: string
          created_at?: string
          name?: string
          type?: LocationType
          latitude?: number
          longitude?: number
          address?: string | null
          city?: string
          state?: string
          country?: string
          postal_code?: string | null
          population?: number | null
          area_sq_km?: number | null
          metadata?: Json | null
        }
      }
      resources: {
        Row: {
          id: string
          created_at: string
          updated_at: string
          disaster_id: string | null
          location_id: string
          type: ResourceType
          name: string
          quantity: number
          unit: string
          status: ResourceStatus
          allocated_to: string | null
          priority: number
          metadata: Json | null
        }
        Insert: {
          id?: string
          created_at?: string
          updated_at?: string
          disaster_id?: string | null
          location_id: string
          type: ResourceType
          name: string
          quantity: number
          unit: string
          status?: ResourceStatus
          allocated_to?: string | null
          priority?: number
          metadata?: Json | null
        }
        Update: {
          id?: string
          created_at?: string
          updated_at?: string
          disaster_id?: string | null
          location_id?: string
          type?: ResourceType
          name?: string
          quantity?: number
          unit?: string
          status?: ResourceStatus
          allocated_to?: string | null
          priority?: number
          metadata?: Json | null
        }
      }
      predictions: {
        Row: {
          id: string
          created_at: string
          disaster_id: string | null
          location_id: string
          model_version: string
          prediction_type: PredictionType
          confidence_score: number
          predicted_severity: DisasterSeverity | null
          predicted_start_date: string | null
          predicted_end_date: string | null
          affected_area_km: number | null
          predicted_casualties: number | null
          features: Json
          metadata: Json | null
        }
        Insert: {
          id?: string
          created_at?: string
          disaster_id?: string | null
          location_id: string
          model_version: string
          prediction_type: PredictionType
          confidence_score: number
          predicted_severity?: DisasterSeverity | null
          predicted_start_date?: string | null
          predicted_end_date?: string | null
          affected_area_km?: number | null
          predicted_casualties?: number | null
          features: Json
          metadata?: Json | null
        }
        Update: {
          id?: string
          created_at?: string
          disaster_id?: string | null
          location_id?: string
          model_version?: string
          prediction_type?: PredictionType
          confidence_score?: number
          predicted_severity?: DisasterSeverity | null
          predicted_start_date?: string | null
          predicted_end_date?: string | null
          affected_area_km?: number | null
          predicted_casualties?: number | null
          features?: Json
          metadata?: Json | null
        }
      }
      users: {
        Row: {
          id: string
          created_at: string
          updated_at: string
          email: string
          role: UserRole
          full_name: string | null
          phone: string | null
          organization: string | null
          metadata: Json | null
          is_profile_completed: boolean
        }
        Insert: {
          id: string
          created_at?: string
          updated_at?: string
          email: string
          role?: UserRole
          full_name?: string | null
          phone?: string | null
          organization?: string | null
          metadata?: Json | null
          is_profile_completed?: boolean
        }
        Update: {
          id?: string
          created_at?: string
          updated_at?: string
          email?: string
          role?: UserRole
          full_name?: string | null
          phone?: string | null
          organization?: string | null
          metadata?: Json | null
          is_profile_completed?: boolean
        }
      }
      resource_requests: {
        Row: {
          id: string
          victim_id: string
          resource_type: string
          quantity: number
          description: string | null
          priority: string
          latitude: number | null
          longitude: number | null
          address_text: string | null
          status: string
          assigned_to: string | null
          assigned_role: string | null
          estimated_delivery: string | null
          attachments: string[]
          rejection_reason: string | null
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          victim_id: string
          resource_type: string
          quantity?: number
          description?: string | null
          priority?: string
          latitude?: number | null
          longitude?: number | null
          address_text?: string | null
          status?: string
          assigned_to?: string | null
          assigned_role?: string | null
          estimated_delivery?: string | null
          attachments?: string[]
          rejection_reason?: string | null
          created_at?: string
          updated_at?: string
        }
        Update: {
          id?: string
          victim_id?: string
          resource_type?: string
          quantity?: number
          description?: string | null
          priority?: string
          latitude?: number | null
          longitude?: number | null
          address_text?: string | null
          status?: string
          assigned_to?: string | null
          assigned_role?: string | null
          estimated_delivery?: string | null
          attachments?: string[]
          rejection_reason?: string | null
          created_at?: string
          updated_at?: string
        }
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      disaster_type: DisasterType
      disaster_severity: DisasterSeverity
      disaster_status: DisasterStatus
      location_type: LocationType
      resource_type: ResourceType
      resource_status: ResourceStatus
      prediction_type: PredictionType
      user_role: UserRole
    }
  }
}

export type DisasterType =
  | 'earthquake'
  | 'flood'
  | 'hurricane'
  | 'tornado'
  | 'wildfire'
  | 'tsunami'
  | 'drought'
  | 'landslide'
  | 'volcano'
  | 'other'

export type DisasterSeverity = 'low' | 'medium' | 'high' | 'critical'

export type DisasterStatus = 'predicted' | 'active' | 'monitoring' | 'resolved'

export type LocationType = 'city' | 'region' | 'shelter' | 'hospital' | 'warehouse'

export type ResourceType =
  | 'food'
  | 'water'
  | 'medical'
  | 'shelter'
  | 'personnel'
  | 'equipment'
  | 'other'

export type ResourceStatus = 'available' | 'allocated' | 'in_transit' | 'deployed'

export type PredictionType = 'severity' | 'spread' | 'duration' | 'impact'

export type UserRole = 'admin' | 'ngo' | 'victim' | 'donor' | 'volunteer'
