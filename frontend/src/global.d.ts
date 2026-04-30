// Global type declarations for non-TS modules

// CSS imports (e.g. maplibre-gl/dist/maplibre-gl.css)
declare module '*.css' {
  const content: Record<string, string>
  export default content
}

// Image asset imports
declare module '*.svg' {
  const content: string
  export default content
}
declare module '*.png' {
  const content: string
  export default content
}
declare module '*.jpg' {
  const content: string
  export default content
}
declare module '*.webp' {
  const content: string
  export default content
}