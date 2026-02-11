# Google OAuth Redirect URI Mismatch Fix

## Error
```
Error 400: redirect_uri_mismatch
You can't sign in because this app sent an invalid request.
```

## Solution

The redirect URIs configured in Google Cloud Console must match your application's callback URL.

### Step 1: Get Your Application URLs

**For Local Development:**
- URL: `http://localhost:3000/auth/callback`

**For Production:**
- URL: `https://your-production-domain.com/auth/callback`

### Step 2: Configure Google Cloud Console

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project
3. Navigate to **APIs & Services** → **Credentials**
4. Click on your OAuth 2.0 Client ID
5. Under **Authorized redirect URIs**, add:
   ```
   http://localhost:3000/auth/callback
   ```
6. Click **Save**

### Step 3: Configure Supabase

1. Go to your [Supabase Dashboard](https://supabase.com/dashboard)
2. Navigate to **Authentication** → **Providers** → **Google**
3. Ensure the redirect URL is configured:
   ```
   https://your-project.supabase.co/auth/v1/callback
   ```
4. Or use the site URL:
   ```
   http://localhost:3000
   ```

### Step 4: Update Environment Variables

Create/Update your `.env.local` file in the frontend directory:

```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

### Step 5: Clear Cache and Retry

1. Clear your browser cache and cookies
2. Try logging in again

## Required Redirect URIs Summary

| Environment | Redirect URI |
|-------------|--------------|
| Development | `http://localhost:3000/auth/callback` |
| Production | `https://your-domain.com/auth/callback` |
| Supabase | `https://your-project.supabase.co/auth/v1/callback` |

## Additional Notes

- Make sure your Supabase project URL is correctly configured
- The callback route is located at `frontend/src/app/auth/callback/route.ts`
- Google OAuth requires the redirect URI to exactly match, including trailing slashes
