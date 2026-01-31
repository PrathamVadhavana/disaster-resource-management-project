/**
 * Authentication & Form Validation Schemas
 * Zod schemas for frontend form validation and type inference
 */

import { z } from 'zod';
import { UserRole } from '@/lib/auth/authTypes';

// ============================================================================
// Authentication Schemas
// ============================================================================

/**
 * Login Form Schema
 * Validates email and password for login
 */
export const loginSchema = z.object({
    email: z
        .string()
        .min(1, 'Email is required')
        .email('Please enter a valid email address'),
    password: z
        .string()
        .min(1, 'Password is required')
        .min(6, 'Password must be at least 6 characters'),
    remember_me: z.boolean().optional().default(false),
});

export type LoginFormData = z.infer<typeof loginSchema>;

/**
 * Signup Form Schema
 * Comprehensive validation for user registration
 */
export const signupSchema = z
    .object({
        email: z
            .string()
            .min(1, 'Email is required')
            .email('Please enter a valid email address'),
        full_name: z
            .string()
            .min(2, 'Name must be at least 2 characters')
            .max(100, 'Name must be less than 100 characters'),
        password: z
            .string()
            .min(8, 'Password must be at least 8 characters')
            .regex(
                /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]/,
                'Password must contain uppercase, lowercase, number, and special character'
            ),
        confirm_password: z
            .string()
            .min(1, 'Please confirm your password'),
        initial_role: z
            .enum([
                UserRole.NGO,
                UserRole.VICTIM,
                UserRole.DONOR,
                UserRole.VOLUNTEER,
            ])
            .optional(),
        terms_accepted: z
            .boolean()
            .refine((val) => val === true, 'You must accept the terms and conditions'),
    })
    .refine((data) => data.password === data.confirm_password, {
        message: "Passwords don't match",
        path: ['confirm_password'],
    });

export type SignupFormData = z.infer<typeof signupSchema>;

/**
 * Email Verification Schema
 * OTP or verification code validation
 */
export const emailVerificationSchema = z.object({
    email: z
        .string()
        .email('Invalid email address'),
    code: z
        .string()
        .min(4, 'Verification code must be at least 4 characters')
        .max(8, 'Verification code must be less than 8 characters'),
});

export type EmailVerificationData = z.infer<typeof emailVerificationSchema>;

/**
 * Role Selection Schema
 * Validates role selection during signup
 */
export const roleSelectionSchema = z.object({
    role: z.enum([
        UserRole.VICTIM,
        UserRole.NGO,
        UserRole.DONOR,
        UserRole.VOLUNTEER,
    ]),
    organization_name: z
        .string()
        .optional()
        .refine(
            (val) => {
                // Required for NGO and RESPONDER roles
                // This will be validated in the component level based on selected role
                return true;
            },
            'Organization name may be required for your role'
        ),
});

export type RoleSelectionData = z.infer<typeof roleSelectionSchema>;

/**
 * Password Reset Request Schema
 * Email validation for password reset initiation
 */
export const passwordResetRequestSchema = z.object({
    email: z
        .string()
        .min(1, 'Email is required')
        .email('Please enter a valid email address'),
});

export type PasswordResetRequestData = z.infer<typeof passwordResetRequestSchema>;

/**
 * Password Reset Confirm Schema
 * New password validation with confirmation
 */
export const passwordResetConfirmSchema = z
    .object({
        token: z.string().min(1, 'Reset token is missing'),
        new_password: z
            .string()
            .min(8, 'Password must be at least 8 characters')
            .regex(
                /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]/,
                'Password must contain uppercase, lowercase, number, and special character'
            ),
        confirm_password: z
            .string()
            .min(1, 'Please confirm your password'),
    })
    .refine((data) => data.new_password === data.confirm_password, {
        message: "Passwords don't match",
        path: ['confirm_password'],
    });

export type PasswordResetConfirmData = z.infer<typeof passwordResetConfirmSchema>;

// ============================================================================
// Profile Schemas
// ============================================================================

/**
 * Profile Update Schema
 * Partial user profile updates
 */
export const profileUpdateSchema = z.object({
    full_name: z
        .string()
        .min(2, 'Name must be at least 2 characters')
        .max(100, 'Name must be less than 100 characters')
        .optional(),
    phone_number: z
        .string()
        .regex(/^[+]?[(]?[0-9]{3}[)]?[-\s.]?[0-9]{3}[-\s.]?[0-9]{4,6}/, 'Invalid phone number')
        .optional()
        .or(z.literal('')),
    organization_name: z
        .string()
        .min(2, 'Organization name must be at least 2 characters')
        .max(255, 'Organization name must be less than 255 characters')
        .optional(),
    location: z
        .object({
            latitude: z.number().min(-90).max(90).optional(),
            longitude: z.number().min(-180).max(180).optional(),
            city: z.string().optional(),
            state: z.string().optional(),
            country: z.string().optional(),
        })
        .optional(),
});

export type ProfileUpdateData = z.infer<typeof profileUpdateSchema>;

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Validates email format according to RFC 5322
 * @param email - Email address to validate
 * @returns boolean - True if valid
 */
export const isValidEmail = (email: string): boolean => {
    return z.string().email().safeParse(email).success;
};

/**
 * Validates password strength
 * Requirements: 8+ chars, uppercase, lowercase, number, special char
 * @param password - Password to validate
 * @returns object with strength level and feedback
 */
export const validatePasswordStrength = (
    password: string
): {
    score: number;
    strength: 'weak' | 'fair' | 'good' | 'strong';
    feedback: string[];
} => {
    const feedback: string[] = [];
    let score = 0;

    if (password.length >= 8) score += 1;
    if (password.length >= 12) score += 1;
    if (/[a-z]/.test(password)) score += 1;
    if (/[A-Z]/.test(password)) score += 1;
    if (/\d/.test(password)) score += 1;
    if (/[@$!%*?&]/.test(password)) score += 1;

    if (password.length < 8) feedback.push('At least 8 characters');
    if (!/[a-z]/.test(password)) feedback.push('At least one lowercase letter');
    if (!/[A-Z]/.test(password)) feedback.push('At least one uppercase letter');
    if (!/\d/.test(password)) feedback.push('At least one number');
    if (!/[@$!%*?&]/.test(password)) feedback.push('At least one special character (@$!%*?&)');

    let strength: 'weak' | 'fair' | 'good' | 'strong';
    if (score < 2) strength = 'weak';
    else if (score < 4) strength = 'fair';
    else if (score < 6) strength = 'good';
    else strength = 'strong';

    return { score, strength, feedback };
};
