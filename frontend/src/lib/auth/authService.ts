// @ts-nocheck — This file is part of the FastAPI backend integration layer (not currently active)
/**
 * Authentication Service
 * Handles all auth API calls and token management
 */

import axios, { AxiosError, AxiosInstance } from 'axios';
import {
    User,
    AuthResponse,
    LoginCredentials,
    SignupData,
    EmailVerificationRequest,
    RoleSelectionData,
    OAuthToken,
    PasswordResetRequest,
    PasswordResetConfirm,
    ApiErrorResponse,
    IAuthService,
} from '@/lib/auth/authTypes';
import { tokenManager } from '@/lib/auth/tokenManager';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Create axios instance with authentication headers
 */
const createAuthClient = (): AxiosInstance => {
    const client = axios.create({
        baseURL: `${API_BASE_URL}/api`,
        timeout: 10000,
        withCredentials: true, // Include cookies in requests
        headers: {
            'Content-Type': 'application/json',
        },
    });

    // Request interceptor: Add authorization header
    client.interceptors.request.use((config) => {
        const token = tokenManager.getToken();
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        // Add CSRF token if available (from cookies)
        const csrfToken = getCsrfToken();
        if (csrfToken) {
            config.headers['X-CSRF-Token'] = csrfToken;
        }
        return config;
    });

    // Response interceptor: Handle token expiration
    client.interceptors.response.use(
        (response) => response,
        async (error: AxiosError) => {
            const originalRequest = error.config as any;

            if (error.response?.status === 401 && !originalRequest._retry) {
                originalRequest._retry = true;

                try {
                    const newToken = await authService.refreshToken();
                    originalRequest.headers.Authorization = `Bearer ${newToken}`;
                    return client(originalRequest);
                } catch {
                    // Refresh failed, redirect to login
                    tokenManager.clearToken();
                    window.location.href = '/login';
                    return Promise.reject(error);
                }
            }

            return Promise.reject(error);
        }
    );

    return client;
};

/**
 * Get CSRF token from cookies
 */
const getCsrfToken = (): string | null => {
    if (typeof document === 'undefined') return null;
    const cookies = document.cookie.split(';');
    for (const cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'csrf_token') {
            return decodeURIComponent(value);
        }
    }
    return null;
};

/**
 * Parse error response and return user-friendly message
 */
const parseError = (error: unknown): string => {
    if (axios.isAxiosError(error)) {
        const data = error.response?.data as ApiErrorResponse | undefined;
        if (data?.detail) {
            if (typeof data.detail === 'string') {
                return data.detail;
            } else if (Array.isArray(data.detail)) {
                return data.detail[0] || 'An error occurred';
            } else if (typeof data.detail === 'object') {
                return Object.values(data.detail)[0]?.[0] || 'An error occurred';
            }
        }
    }
    return error instanceof Error ? error.message : 'An unexpected error occurred';
};

/**
 * Authentication Service
 * Implements IAuthService interface for all auth operations
 */
class AuthService implements IAuthService {
    private client: AxiosInstance;

    constructor() {
        this.client = createAuthClient();
    }

    /**
     * Login with email and password
     */
    async login(credentials: LoginCredentials): Promise<AuthResponse> {
        try {
            const response = await this.client.post<AuthResponse>('/auth/login', {
                email: credentials.email,
                password: credentials.password,
            });

            const { access_token, user } = response.data;

            // Store token securely
            tokenManager.setToken(access_token);

            // Optional: Store refresh token if provided
            if (response.data.refresh_token) {
                tokenManager.setRefreshToken(response.data.refresh_token);
            }

            return response.data;
        } catch (error) {
            throw new Error(parseError(error));
        }
    }

    /**
     * Register new user with email and password
     */
    async signup(data: SignupData): Promise<AuthResponse> {
        try {
            const response = await this.client.post<AuthResponse>('/auth/register', {
                email: data.email,
                password: data.password,
                full_name: data.full_name,
                initial_role: data.initial_role,
            });

            const { access_token } = response.data;
            tokenManager.setToken(access_token);

            if (response.data.refresh_token) {
                tokenManager.setRefreshToken(response.data.refresh_token);
            }

            return response.data;
        } catch (error) {
            throw new Error(parseError(error));
        }
    }

    /**
     * Logout user
     */
    async logout(): Promise<void> {
        try {
            await this.client.post('/auth/logout');
        } catch (error) {
            console.warn('Logout API error:', error);
        } finally {
            tokenManager.clearToken();
            tokenManager.clearRefreshToken();
        }
    }

    /**
     * Verify email with OTP or verification code
     */
    async verifyEmail(data: EmailVerificationRequest): Promise<User> {
        try {
            const response = await this.client.post<User>('/auth/verify-email', {
                email: data.email,
                code: data.code,
            });

            return response.data;
        } catch (error) {
            throw new Error(parseError(error));
        }
    }

    /**
     * Resend verification email
     */
    async resendVerificationEmail(email: string): Promise<void> {
        try {
            await this.client.post('/auth/resend-verification', { email });
        } catch (error) {
            throw new Error(parseError(error));
        }
    }

    /**
     * Select or update user role
     */
    async selectRole(data: RoleSelectionData): Promise<User> {
        try {
            const response = await this.client.post<User>('/auth/select-role', {
                role: data.role,
                organization_name: data.organization_name,
                additional_info: data.additional_info,
            });

            return response.data;
        } catch (error) {
            throw new Error(parseError(error));
        }
    }

    /**
     * Login with Google OAuth
     */
    async googleLogin(token: OAuthToken): Promise<AuthResponse> {
        try {
            const response = await this.client.post<AuthResponse>('/auth/google-callback', {
                code: token.code,
                state: token.state,
                id_token: token.id_token,
            });

            const { access_token } = response.data;
            tokenManager.setToken(access_token);

            if (response.data.refresh_token) {
                tokenManager.setRefreshToken(response.data.refresh_token);
            }

            return response.data;
        } catch (error) {
            throw new Error(parseError(error));
        }
    }

    /**
     * Refresh access token using refresh token
     */
    async refreshToken(): Promise<string> {
        try {
            const refreshToken = tokenManager.getRefreshToken();
            if (!refreshToken) {
                throw new Error('No refresh token available');
            }

            const response = await this.client.post<{ access_token: string }>(
                '/auth/refresh',
                { refresh_token: refreshToken }
            );

            const newAccessToken = response.data.access_token;
            tokenManager.setToken(newAccessToken);

            return newAccessToken;
        } catch (error) {
            tokenManager.clearToken();
            tokenManager.clearRefreshToken();
            throw new Error(parseError(error));
        }
    }

    /**
     * Get current authenticated user
     */
    async getCurrentUser(): Promise<User | null> {
        try {
            const response = await this.client.get<User>('/auth/me');
            return response.data;
        } catch (error) {
            tokenManager.clearToken();
            return null;
        }
    }

    /**
     * Update user profile
     */
    async updateProfile(data: Partial<User>): Promise<User> {
        try {
            const response = await this.client.patch<User>('/auth/profile', data);
            return response.data;
        } catch (error) {
            throw new Error(parseError(error));
        }
    }

    /**
     * Request password reset
     */
    async requestPasswordReset(data: PasswordResetRequest): Promise<void> {
        try {
            await this.client.post('/auth/password-reset-request', {
                email: data.email,
            });
        } catch (error) {
            throw new Error(parseError(error));
        }
    }

    /**
     * Confirm password reset with token
     */
    async resetPassword(data: PasswordResetConfirm): Promise<void> {
        try {
            await this.client.post('/auth/password-reset-confirm', {
                token: data.token,
                new_password: data.new_password,
            });
        } catch (error) {
            throw new Error(parseError(error));
        }
    }

    /**
     * Verify CSRF token (called on page load)
     */
    async verifyCsrfToken(): Promise<string> {
        try {
            const response = await this.client.get<{ csrf_token: string }>(
                '/auth/csrf-token'
            );
            return response.data.csrf_token;
        } catch (error) {
            console.warn('CSRF token verification failed:', error);
            return '';
        }
    }
}

// Export singleton instance
export const authService = new AuthService();

// Export type
export type { IAuthService };
