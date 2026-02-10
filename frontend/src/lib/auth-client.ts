// @ts-nocheck — This file is part of the FastAPI backend integration layer (not currently active)
/**
 * Auth Client Integration Layer
 * Handles communication with FastAPI backend for authentication
 */

export interface AuthResponse {
    access_token: string;
    token_type: string;
    user: {
        id: string;
        email: string;
        role: string;
        created_at: string;
    };
}

export interface AuthCredentials {
    email: string;
    password: string;
}

export interface SignupData extends AuthCredentials {
    full_name?: string;
    role?: string;
}

class AuthClient {
    private baseUrl: string;
    private tokenKey = 'disaster_relief_token';

    constructor(baseUrl: string = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') {
        this.baseUrl = baseUrl;
    }

    /**
     * Get the stored authentication token
     */
    getToken(): string | null {
        if (typeof window === 'undefined') return null;
        return localStorage.getItem(this.tokenKey);
    }

    /**
     * Store the authentication token
     */
    setToken(token: string): void {
        if (typeof window === 'undefined') return;
        localStorage.setItem(this.tokenKey, token);
    }

    /**
     * Clear the authentication token
     */
    clearToken(): void {
        if (typeof window === 'undefined') return;
        localStorage.removeItem(this.tokenKey);
    }

    /**
     * Get authorization headers
     */
    private getAuthHeaders(): Record<string, string> {
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
        };

        const token = this.getToken();
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        return headers;
    }

    /**
     * Login with email and password
     */
    async login(credentials: AuthCredentials): Promise<AuthResponse> {
        const response = await fetch(`${this.baseUrl}/api/auth/login`, {
            method: 'POST',
            headers: this.getAuthHeaders(),
            body: JSON.stringify(credentials),
            credentials: 'include',
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Login failed');
        }

        const data: AuthResponse = await response.json();
        this.setToken(data.access_token);
        return data;
    }

    /**
     * Register a new user
     */
    async register(data: SignupData): Promise<AuthResponse> {
        const response = await fetch(`${this.baseUrl}/api/auth/register`, {
            method: 'POST',
            headers: this.getAuthHeaders(),
            body: JSON.stringify(data),
            credentials: 'include',
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Registration failed');
        }

        const result: AuthResponse = await response.json();
        this.setToken(result.access_token);
        return result;
    }

    /**
     * Verify email with OTP
     */
    async verifyEmail(email: string, otp: string): Promise<{ success: boolean }> {
        const response = await fetch(`${this.baseUrl}/api/auth/verify-email`, {
            method: 'POST',
            headers: this.getAuthHeaders(),
            body: JSON.stringify({ email, otp }),
            credentials: 'include',
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Email verification failed');
        }

        return response.json();
    }

    /**
     * Select user role
     */
    async selectRole(role: string): Promise<{ success: boolean }> {
        const response = await fetch(`${this.baseUrl}/api/auth/select-role`, {
            method: 'POST',
            headers: this.getAuthHeaders(),
            body: JSON.stringify({ role }),
            credentials: 'include',
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Role selection failed');
        }

        return response.json();
    }

    /**
     * Refresh authentication token
     */
    async refreshToken(): Promise<AuthResponse> {
        const response = await fetch(`${this.baseUrl}/api/auth/refresh`, {
            method: 'POST',
            headers: this.getAuthHeaders(),
            credentials: 'include',
        });

        if (!response.ok) {
            this.clearToken();
            throw new Error('Token refresh failed');
        }

        const data: AuthResponse = await response.json();
        this.setToken(data.access_token);
        return data;
    }

    /**
     * Logout user
     */
    async logout(): Promise<void> {
        try {
            await fetch(`${this.baseUrl}/api/auth/logout`, {
                method: 'POST',
                headers: this.getAuthHeaders(),
                credentials: 'include',
            });
        } finally {
            this.clearToken();
        }
    }

    /**
     * Get current user info
     */
    async getMe(): Promise<AuthResponse['user']> {
        const response = await fetch(`${this.baseUrl}/api/auth/me`, {
            method: 'GET',
            headers: this.getAuthHeaders(),
            credentials: 'include',
        });

        if (!response.ok) {
            if (response.status === 401) {
                this.clearToken();
            }
            throw new Error('Failed to fetch user info');
        }

        return response.json();
    }

    /**
     * Request password reset
     */
    async requestPasswordReset(email: string): Promise<{ success: boolean }> {
        const response = await fetch(`${this.baseUrl}/api/auth/request-password-reset`, {
            method: 'POST',
            headers: this.getAuthHeaders(),
            body: JSON.stringify({ email }),
            credentials: 'include',
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Password reset request failed');
        }

        return response.json();
    }

    /**
     * Reset password with token
     */
    async resetPassword(token: string, newPassword: string): Promise<{ success: boolean }> {
        const response = await fetch(`${this.baseUrl}/api/auth/reset-password`, {
            method: 'POST',
            headers: this.getAuthHeaders(),
            body: JSON.stringify({ token, new_password: newPassword }),
            credentials: 'include',
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Password reset failed');
        }

        return response.json();
    }

    /**
     * Google OAuth login
     */
    async googleLogin(token: string): Promise<AuthResponse> {
        const response = await fetch(`${this.baseUrl}/api/auth/google`, {
            method: 'POST',
            headers: this.getAuthHeaders(),
            body: JSON.stringify({ token }),
            credentials: 'include',
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Google login failed');
        }

        const data: AuthResponse = await response.json();
        this.setToken(data.access_token);
        return data;
    }
}

// Export singleton instance
export const authClient = new AuthClient();