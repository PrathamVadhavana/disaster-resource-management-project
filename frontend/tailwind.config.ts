import type { Config } from 'tailwindcss'

/**
 * Tailwind CSS v4 Configuration
 *
 * Colors, fonts, border-radius, keyframes, and animations are defined in
 * globals.css via the @theme block (the v4 canonical approach).
 * Only content paths and non-theme config live here to avoid duplication.
 */
const config: Config = {
  darkMode: 'class',
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      // Emergency severity palette (not duplicated in @theme)
      colors: {
        emergency: {
          critical: '#DC2626',
          high: '#EA580C',
          medium: '#F59E0B',
          low: '#10B981',
        },
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
export default config
