// @ts-nocheck — This file is part of the FastAPI backend integration layer (not currently active)
/**
 * Token Manager
 * Secure token storage and management using HttpOnly cookies
 * Falls back to in-memory storage for React state
 */

const TOKEN_KEY = 'auth_token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const TOKEN_EXPIRY_KEY = 'token_expiry';

// In-memory storage (primary for security)
let tokenCache: string | null = null;
let refreshTokenCache: string | null = null;

class TokenManager {
    /**
     * Set access token
     * In production, this should be set via HttpOnly cookie from backend
     */
    setToken(token: string): void {
        tokenCache = token;

        // Optionally store in localStorage as backup (NOT SECURE - only for dev)
        if (process.env.NODE_ENV === 'development') {
            try {
                localStorage.setItem(TOKEN_KEY, token);
                const decoded = this.decodeToken(token);
                if (decoded && decoded.exp) {
                    localStorage.setItem(TOKEN_EXPIRY_KEY, decoded.exp.toString());
                }
            } catch (e) {
                // localStorage might not be available (SSR context)
            }
        }
    }

    /**
     * Get access token from memory cache
     */
    getToken(): string | null {
        if (tokenCache) {
            return tokenCache;
        }

        // Fallback to localStorage in development
        if (process.env.NODE_ENV === 'development') {
            try {
                const token = localStorage.getItem(TOKEN_KEY);
                if (token && !this.isTokenExpired(token)) {
                    tokenCache = token;
                    return token;
                }
            } catch (e) {
                // localStorage might not be available
            }
        }

        return null;
    }

    /**
     * Set refresh token
     */
    setRefreshToken(token: string): void {
        refreshTokenCache = token;

        // In development only
        if (process.env.NODE_ENV === 'development') {
            try {
                localStorage.setItem(REFRESH_TOKEN_KEY, token);
            } catch (e) {
                // localStorage might not be available
            }
        }
    }

    /**
     * Get refresh token
     */
    getRefreshToken(): string | null {
        if (refreshTokenCache) {
            return refreshTokenCache;
        }

        if (process.env.NODE_ENV === 'development') {
            try {
                const token = localStorage.getItem(REFRESH_TOKEN_KEY);
                if (token) {
                    refreshTokenCache = token;
                    return token;
                }
            } catch (e) {
                // localStorage might not be available
            }
        }

        return null;
    }

    /**
     * Clear all tokens
     */
    clearToken(): void {
        tokenCache = null;

        if (process.env.NODE_ENV === 'development') {
            try {
                localStorage.removeItem(TOKEN_KEY);
                localStorage.removeItem(TOKEN_EXPIRY_KEY);
            } catch (e) {
                // localStorage might not be available
            }
        }
    }

    /**
     * Clear refresh token
     */
    clearRefreshToken(): void {
        refreshTokenCache = null;

        if (process.env.NODE_ENV === 'development') {
            try {
                localStorage.removeItem(REFRESH_TOKEN_KEY);
            } catch (e) {
                // localStorage might not be available
            }
        }
    }

    /**
     * Clear all authentication data
     */
    clearAllTokens(): void {
        this.clearToken();
        this.clearRefreshToken();
    }

    /**
     * Decode JWT token (without verification - only for client-side)
     * Note: Always verify token on backend
     */
    decodeToken(token: string): Record<string, any> | null {
        try {
            const parts = token.split('.');
            if (parts.length !== 3) return null;

            const decoded = JSON.parse(
                Buffer.from(parts[1], 'base64').toString('utf-8')
            );
            return decoded;
        } catch (e) {
            console.error('Failed to decode token:', e);
            return null;
        }
    }

    /**
     * Check if token is expired
     */
    isTokenExpired(token?: string): boolean {
        const tkn = token || this.getToken();
        if (!tkn) return true;

        const decoded = this.decodeToken(tkn);
        if (!decoded || !decoded.exp) return true;

        const expirationTime = decoded.exp * 1000; // Convert to milliseconds
        const currentTime = Date.now();

        // Consider token expired if it expires within 1 minute
        return expirationTime - currentTime < 60000;
    }

    /**
     * Get remaining time until token expiration (in seconds)
     */
    getTokenExpirationTime(): number | null {
        const token = this.getToken();
        if (!token) return null;

        const decoded = this.decodeToken(token);
        if (!decoded || !decoded.exp) return null;

        const expirationTime = decoded.exp * 1000; // Convert to milliseconds
        const remainingTime = expirationTime - Date.now();

        return remainingTime > 0 ? Math.floor(remainingTime / 1000) : 0;
    }

    /**
     * Check if user is authenticated
     */
    isAuthenticated(): boolean {
        const token = this.getToken();
        return !!token && !this.isTokenExpired(token);
    }

    /**
     * Get token from HttpOnly cookie (server-side or from next.js request)
     * This is the preferred method in production
     */
    getTokenFromCookie(cookieString?: string): string | null {
        const cookies = cookieString || (typeof document !== 'undefined' ? document.cookie : '');
        const cookies_array = cookies.split(';');

        for (let cookie of cookies_array) {
            const cookie_parts = cookie.trim().split('=');
            if (cookie_parts[0] === 'auth_token' || cookie_parts[0] === 'accessToken') {
                return decodeURIComponent(cookie_parts[1]);
            }
        }

        return null;
    }

    /**
     * Set cookie (used by next.js during auth callback)
     * In production, backend should set HttpOnly cookies
     */
    setCookie(name: string, value: string, days: number = 7): void {
        if (typeof document === 'undefined') return; // SSR guard

        const date = new Date();
        date.setTime(date.getTime() + days * 24 * 60 * 60 * 1000);
        const expires = `expires=${date.toUTCString()}`;
        const secure = process.env.NODE_ENV === 'production' ? 'Secure;' : '';
        const sameSite = 'SameSite=Strict;';

        document.cookie = `${name}=${encodeURIComponent(value)};${expires};Path=/;${secure}${sameSite}`;
    }

    /**
     * Get cookie by name
     */
    getCookie(name: string): string | null {
        if (typeof document === 'undefined') return null;

        const nameEQ = name + '=';
        const cookies = document.cookie.split(';');

        for (let cookie of cookies) {
            const trimmed = cookie.trim();
            if (trimmed.indexOf(nameEQ) === 0) {
                return decodeURIComponent(trimmed.substring(nameEQ.length));
            }
        }

        return null;
    }

    /**
     * Delete cookie
     */
    deleteCookie(name: string): void {
        if (typeof document === 'undefined') return;

        document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 UTC;Path=/;`;
    }
}

// Export singleton instance
export const tokenManager = new TokenManager();

/**
 * Get auth header for API requests
 */
export const getAuthHeader = (): Record<string, string> => {
    const token = tokenManager.getToken();
    if (!token) return {};

    return {
        Authorization: `Bearer ${token}`,
    };
};

/**
 * Check if user has valid auth token
 */
export const hasAuthToken = (): boolean => {
    return tokenManager.isAuthenticated();
};
