'use client';

/**
 * SignupForm - Email-based signup component
 * 
 * This is a convenience wrapper that renders the AuthForm with signup view.
 * All phone-based OTP authentication has been removed in favor of email-based auth.
 */

import AuthForm from '@/components/auth/AuthForm';

export default function SignupForm() {
    return <AuthForm initialView="signup" />;
}
