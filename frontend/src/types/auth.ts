import { z } from 'zod';

// Enum matches database "user_role"
export const UserRoleEnum = z.enum(['victim', 'donor', 'ngo', 'volunteer', 'admin']);
export type UserRole = z.infer<typeof UserRoleEnum>;

// OTP verification schema (used for email OTP)
export const otpSchema = z.object({
    code: z.string().length(6, "OTP must be exactly 6 digits"),
});

export type OtpValues = z.infer<typeof otpSchema>;

// Extension Schemas (for Onboarding)

export const victimDetailsSchema = z.object({
    current_status: z.enum(['safe', 'needs_help', 'critical', 'evacuated']),
    needs: z.array(z.string()).min(1, "Select at least one need"),
    medical_needs: z.string().optional(),
    location: z.object({
        lat: z.number(),
        lng: z.number()
    }).optional()
});

export const ngoDetailsSchema = z.object({
    organization_name: z.string().min(2, "Organization name is required"),
    registration_number: z.string().min(2, "Registration number is required"),
    operating_sectors: z.array(z.string()).min(1, "Select at least one sector"),
    website: z.string().url().optional().or(z.literal('')),
});
