/**
 * Supabase Storage upload utilities.
 *
 * Provides helper functions for uploading files (e.g. victim request
 * attachments, verification documents) to Supabase Storage and
 * returning their public download URLs.
 *
 * Usage:
 *   import { uploadFile, uploadMultipleFiles } from '@/lib/supabase/storage'
 *   const url = await uploadFile(file, 'attachments/request-123')
 */
import { getSupabaseClient } from './client'

const BUCKET = 'uploads'

/**
 * Upload a single file to Supabase Storage.
 *
 * @param file - The File object to upload
 * @param path - Storage path (folder), e.g. 'attachments/request-123'
 * @returns The public download URL of the uploaded file
 */
export async function uploadFile(file: File, path: string): Promise<string> {
    const sb = getSupabaseClient()
    const safeName = `${Date.now()}_${file.name.replace(/[^a-zA-Z0-9._-]/g, '_')}`
    const fullPath = `${path}/${safeName}`

    const { error } = await sb.storage.from(BUCKET).upload(fullPath, file, {
        contentType: file.type,
        upsert: false,
    })
    if (error) throw error

    const { data } = sb.storage.from(BUCKET).getPublicUrl(fullPath)
    return data.publicUrl
}

/**
 * Upload multiple files in parallel.
 *
 * @param files - Array of File objects
 * @param path  - Storage folder path
 * @returns Array of download URLs (same order as input files)
 */
export async function uploadMultipleFiles(
    files: File[],
    path: string,
): Promise<string[]> {
    return Promise.all(files.map((file) => uploadFile(file, path)))
}
