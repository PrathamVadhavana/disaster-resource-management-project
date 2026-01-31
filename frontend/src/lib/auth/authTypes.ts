/**
 * Auth Type Definitions
 * Comprehensive TypeScript types for authentication flows
 */

// User Roles - Matches backend schema
export enum UserRole {
    VICTIM = 'victim',
    NGO = 'ngo',
    DONOR = 'donor',
    VOLUNTEER = 'volunteer',
    ADMIN = 'admin',
}

// Auth Status
export enum AuthStatus {
    IDLE = 'idle',
    LOADING = 'loading',
    AUTHENTICATED = 'authenticated',
    UNAUTHENTICATED = 'unauthenticated',
    EMAIL_VERIFICATION_PENDING = 'email_verification_pending',
    ROLE_SELECTION_PENDING = 'role_selection_pending',
    ERROR = 'error',
}

// User Profile
export interface User {
    id: string;
    email: string;
    full_name?: string;
    role: UserRole;
    email_verified: boolean;
    avatar_url?: string;
    phone_number?: string;
    organization_name?: string;
    location?: {
        latitude: number;
        longitude: number;
        city: string;
        state: string;
        country: string;
    };
    metadata?: Record<string, unknown>;
    created_at: string;
    updated_at: string;
    last_login?: string;
}

// Authentication Response
export interface AuthResponse {
    access_token: string;
    refresh_token?: string;
    token_type: string;
    user: User;
    expires_in: number;
}

// Token Payload (decoded JWT)
export interface TokenPayload {
    sub: string; // User ID
    email: string;
    role: UserRole;
    iat: number; // Issued at
    exp: number; // Expiration
    aud?: string; // Audience
}

// Login Request
export interface LoginCredentials {
    email: string;
    password: string;
    remember_me?: boolean;
}

// Signup Request
export interface SignupData {
    email: string;
    password: string;
    confirm_password: string;
    full_name: string;
    initial_role?: UserRole; // Optional initial role
    terms_accepted: boolean;
}

// Email Verification
export interface EmailVerificationRequest {
    email: string;
    code: string; // OTP or token
}

// Role Selection
export interface RoleSelectionData {
    role: UserRole;
    organization_name?: string;
    additional_info?: Record<string, unknown>;
}

// OAuth Response
export interface OAuthToken {
    code: string;
    state?: string;
    id_token?: string;
}

// Google OAuth User Info
export interface GoogleUserInfo {
    id: string;
    email: string;
    verified_email: boolean;
    name: string;
    picture: string;
    locale?: string;
}

// Password Reset
export interface PasswordResetRequest {
    email: string;
}

export interface PasswordResetConfirm {
    token: string;
    new_password: string;
    confirm_password: string;
}

// Error Response
export interface ApiErrorResponse {
    detail: string | string[] | Record<string, string[]>;
    status: number;
    type?: string;
}

// Auth Context/Store State
export interface AuthContextState {
    user: User | null;
    token: string | null;
    status: AuthStatus;
    error: string | null;
    isLoading: boolean;
    isEmailVerificationPending: boolean;
    isRoleSelectionPending: boolean;
}

// Auth Service Methods
export interface IAuthService {
    login(credentials: LoginCredentials): Promise<AuthResponse>;
    signup(data: SignupData): Promise<AuthResponse>;
    logout(): Promise<void>;
    verifyEmail(data: EmailVerificationRequest): Promise<User>;
    selectRole(data: RoleSelectionData): Promise<User>;
    googleLogin(token: OAuthToken): Promise<AuthResponse>;
    refreshToken(): Promise<string>;
    getCurrentUser(): Promise<User | null>;
    updateProfile(data: Partial<User>): Promise<User>;
    requestPasswordReset(data: PasswordResetRequest): Promise<void>;
    resetPassword(data: PasswordResetConfirm): Promise<void>;
}

// Role Display Metadata
export const ROLE_METADATA: Record<UserRole, {
    label: string;
    description: string;
    icon: string;
    color: string;
    bgColor: string;
}> = {
    [UserRole.VICTIM]: {
        label: 'I Need Help (Victim)',
        description: 'I need urgent assistance or resources.',
        icon: '🆘',
        color: 'text-red-600',
        bgColor: 'bg-red-50',
    },
    [UserRole.NGO]: {
        label: 'NGO / Organization',
        description: 'We are coordinating large-scale relief efforts.',
        icon: '🏢',
        color: 'text-blue-600',
        bgColor: 'bg-blue-50',
    },
    [UserRole.DONOR]: {
        label: 'Donor',
        description: 'I want to provide funding or resources.',
        icon: '💝',
        color: 'text-emerald-600',
        bgColor: 'bg-emerald-50',
    },
    [UserRole.VOLUNTEER]: {
        label: 'Volunteer',
        description: 'I want to offer my time and skills.',
        icon: '🤝',
        color: 'text-orange-600',
        bgColor: 'bg-orange-50',
    },
    [UserRole.ADMIN]: {
        label: 'Administrator',
        description: 'Platform oversight and management.',
        icon: '🛡️',
        color: 'text-slate-600',
        bgColor: 'bg-slate-50',
    },
};
