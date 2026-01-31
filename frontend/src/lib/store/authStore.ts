/**
 * Auth Store (Zustand)
 * Global state management for authentication
 */

import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import {
    User,
    AuthStatus,
    LoginCredentials,
    SignupData,
    RoleSelectionData,
    OAuthToken,
    EmailVerificationRequest,
} from '@/lib/auth/authTypes';
import { authService } from '@/lib/auth/authService';
import { tokenManager } from '@/lib/auth/tokenManager';

interface AuthStore {
    // State
    user: User | null;
    token: string | null;
    status: AuthStatus;
    error: string | null;
    isLoading: boolean;
    isEmailVerificationPending: boolean;
    isRoleSelectionPending: boolean;

    // Actions
    login: (credentials: LoginCredentials) => Promise<void>;
    signup: (data: SignupData) => Promise<void>;
    logout: () => Promise<void>;
    verifyEmail: (data: EmailVerificationRequest) => Promise<void>;
    selectRole: (data: RoleSelectionData) => Promise<void>;
    googleLogin: (token: OAuthToken) => Promise<void>;
    initializeAuth: () => Promise<void>;
    setError: (error: string | null) => void;
    clearError: () => void;
    updateUser: (user: Partial<User>) => void;
    reset: () => void;
}

/**
 * Default auth state
 */
const initialState = {
    user: null,
    token: null,
    status: AuthStatus.IDLE,
    error: null,
    isLoading: false,
    isEmailVerificationPending: false,
    isRoleSelectionPending: false,
};

/**
 * Create auth store with persistence
 */
export const useAuthStore = create<AuthStore>()(
    devtools(
        persist(
            (set, get) => ({
                ...initialState,

                /**
                 * Login with email and password
                 */
                login: async (credentials: LoginCredentials) => {
                    set({ isLoading: true, error: null, status: AuthStatus.LOADING });
                    try {
                        const response = await authService.login(credentials);

                        set({
                            user: response.user,
                            token: response.access_token,
                            status: AuthStatus.AUTHENTICATED,
                            isLoading: false,
                            error: null,
                        });

                        // Check if email verification is pending
                        if (!response.user.email_verified) {
                            set({ status: AuthStatus.EMAIL_VERIFICATION_PENDING });
                        }
                    } catch (error) {
                        const errorMessage =
                            error instanceof Error ? error.message : 'Login failed';
                        set({
                            status: AuthStatus.ERROR,
                            error: errorMessage,
                            isLoading: false,
                            token: null,
                            user: null,
                        });
                        throw error;
                    }
                },

                /**
                 * Register new user
                 */
                signup: async (data: SignupData) => {
                    set({ isLoading: true, error: null, status: AuthStatus.LOADING });
                    try {
                        const response = await authService.signup(data);

                        set({
                            user: response.user,
                            token: response.access_token,
                            status: AuthStatus.EMAIL_VERIFICATION_PENDING,
                            isLoading: false,
                            error: null,
                            isEmailVerificationPending: true,
                        });
                    } catch (error) {
                        const errorMessage =
                            error instanceof Error ? error.message : 'Signup failed';
                        set({
                            status: AuthStatus.ERROR,
                            error: errorMessage,
                            isLoading: false,
                            token: null,
                            user: null,
                        });
                        throw error;
                    }
                },

                /**
                 * Logout user
                 */
                logout: async () => {
                    set({ isLoading: true });
                    try {
                        await authService.logout();
                        tokenManager.clearAllTokens();
                        set({ ...initialState, status: AuthStatus.UNAUTHENTICATED });
                    } catch (error) {
                        console.error('Logout error:', error);
                        // Clear state even if API call fails
                        tokenManager.clearAllTokens();
                        set({ ...initialState, status: AuthStatus.UNAUTHENTICATED });
                    }
                },

                /**
                 * Verify email with OTP
                 */
                verifyEmail: async (data: EmailVerificationRequest) => {
                    set({ isLoading: true, error: null });
                    try {
                        const user = await authService.verifyEmail(data);
                        set({
                            user: {
                                ...get().user!,
                                ...user,
                                email_verified: true,
                            },
                            isEmailVerificationPending: false,
                            isLoading: false,
                            status: AuthStatus.ROLE_SELECTION_PENDING,
                        });
                    } catch (error) {
                        const errorMessage =
                            error instanceof Error ? error.message : 'Email verification failed';
                        set({
                            error: errorMessage,
                            isLoading: false,
                        });
                        throw error;
                    }
                },

                /**
                 * Select user role
                 */
                selectRole: async (data: RoleSelectionData) => {
                    set({ isLoading: true, error: null });
                    try {
                        const user = await authService.selectRole(data);
                        set({
                            user,
                            isRoleSelectionPending: false,
                            isLoading: false,
                            status: AuthStatus.AUTHENTICATED,
                        });
                    } catch (error) {
                        const errorMessage =
                            error instanceof Error ? error.message : 'Role selection failed';
                        set({
                            error: errorMessage,
                            isLoading: false,
                        });
                        throw error;
                    }
                },

                /**
                 * Google OAuth login
                 */
                googleLogin: async (token: OAuthToken) => {
                    set({ isLoading: true, error: null, status: AuthStatus.LOADING });
                    try {
                        const response = await authService.googleLogin(token);

                        const newStatus = response.user.email_verified
                            ? AuthStatus.AUTHENTICATED
                            : AuthStatus.EMAIL_VERIFICATION_PENDING;

                        set({
                            user: response.user,
                            token: response.access_token,
                            status: newStatus,
                            isLoading: false,
                            error: null,
                            isEmailVerificationPending: !response.user.email_verified,
                        });
                    } catch (error) {
                        const errorMessage =
                            error instanceof Error ? error.message : 'Google login failed';
                        set({
                            status: AuthStatus.ERROR,
                            error: errorMessage,
                            isLoading: false,
                            token: null,
                            user: null,
                        });
                        throw error;
                    }
                },

                /**
                 * Initialize auth state (check if user is logged in)
                 */
                initializeAuth: async () => {
                    set({ isLoading: true });
                    try {
                        // Check if token exists
                        const token = tokenManager.getToken();
                        if (!token || tokenManager.isTokenExpired()) {
                            set({
                                ...initialState,
                                status: AuthStatus.UNAUTHENTICATED,
                                isLoading: false,
                            });
                            return;
                        }

                        // Fetch current user
                        const user = await authService.getCurrentUser();
                        if (user) {
                            set({
                                user,
                                token,
                                status: AuthStatus.AUTHENTICATED,
                                isLoading: false,
                            });
                        } else {
                            set({
                                ...initialState,
                                status: AuthStatus.UNAUTHENTICATED,
                                isLoading: false,
                            });
                        }
                    } catch (error) {
                        console.error('Auth initialization error:', error);
                        set({
                            ...initialState,
                            status: AuthStatus.UNAUTHENTICATED,
                            isLoading: false,
                        });
                    }
                },

                /**
                 * Set error message
                 */
                setError: (error: string | null) => {
                    set({ error, status: error ? AuthStatus.ERROR : AuthStatus.IDLE });
                },

                /**
                 * Clear error
                 */
                clearError: () => {
                    set({ error: null });
                },

                /**
                 * Update user information
                 */
                updateUser: (userData: Partial<User>) => {
                    const currentUser = get().user;
                    if (currentUser) {
                        set({
                            user: {
                                ...currentUser,
                                ...userData,
                                updated_at: new Date().toISOString(),
                            },
                        });
                    }
                },

                /**
                 * Reset auth state
                 */
                reset: () => {
                    tokenManager.clearAllTokens();
                    set(initialState);
                },
            }),
            {
                name: 'auth-store',
                // Only persist user and token in development
                partialize: (state) =>
                    process.env.NODE_ENV === 'development'
                        ? {
                            user: state.user,
                            token: state.token,
                        }
                        : {},
            }
        ),
        { name: 'AuthStore' }
    )
);

/**
 * Selectors for auth store (for performance optimization)
 */
export const useAuthUser = () => useAuthStore((state) => state.user);
export const useAuthStatus = () => useAuthStore((state) => state.status);
export const useAuthError = () => useAuthStore((state) => state.error);
export const useAuthLoading = () => useAuthStore((state) => state.isLoading);
export const useIsAuthenticated = () =>
    useAuthStore((state) => state.status === AuthStatus.AUTHENTICATED);
export const useIsEmailVerificationPending = () =>
    useAuthStore((state) => state.isEmailVerificationPending);
export const useIsRoleSelectionPending = () =>
    useAuthStore((state) => state.isRoleSelectionPending);
