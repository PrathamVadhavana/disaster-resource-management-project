import dynamic from 'next/dynamic'

// Dynamically import DisasterMap with SSR disabled to avoid window issues
const DisasterMap = dynamic(() => import('@/components/map/disaster-map').then(mod => {
  console.log('DisasterMap module loaded successfully')
  return { default: mod.DisasterMap }
}).catch(error => {
  console.error('Failed to load DisasterMap:', error)
  return { default: () => (
    <div className="h-full w-full flex items-center justify-center bg-red-50 rounded-lg border-2 border-red-200">
      <div className="text-center text-red-600">
        <p className="font-medium">Map failed to load</p>
        <p className="text-sm mt-1">Check browser console for errors</p>
        <p className="text-xs mt-2">{error.message}</p>
      </div>
    </div>
  )}
}), {
  ssr: false,
  loading: () => (
    <div className="h-full w-full flex items-center justify-center bg-blue-50 rounded-lg border-2 border-blue-200">
      <div className="text-center">
        <div className="animate-spin h-12 w-12 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4" />
        <p className="text-blue-700 font-medium">Loading interactive map...</p>
        <p className="text-xs text-blue-600 mt-2">Initializing Leaflet and connecting to database</p>
      </div>
    </div>
  )
})

export default function Home() {
  return (
    <main className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">
            Disaster Management System
          </h1>
          <p className="text-muted-foreground">
            AI-powered disaster prediction and resource allocation platform
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Map */}
          <div className="lg:col-span-2">
            <div className="bg-card rounded-lg border p-6">
              <h2 className="text-2xl font-semibold mb-4">Disaster Map</h2>
              <div className="h-[600px] w-full">
                <DisasterMap />
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Quick Stats */}
            <div className="bg-card rounded-lg border p-6">
              <h3 className="text-lg font-semibold mb-4">System Status</h3>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">Backend</span>
                  <span className="text-sm font-medium text-green-600">Online</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">Database</span>
                  <span className="text-sm font-medium text-yellow-600">Connecting</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">ML Models</span>
                  <span className="text-sm font-medium text-blue-600">Loading</span>
                </div>
              </div>
            </div>

            {/* Quick Actions */}
            <div className="bg-card rounded-lg border p-6">
              <h3 className="text-lg font-semibold mb-4">Quick Actions</h3>
              <div className="space-y-2">
                <button className="w-full bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-medium hover:bg-primary/90 transition-colors">
                  Report Disaster
                </button>
                <button className="w-full bg-secondary text-secondary-foreground px-4 py-2 rounded-md text-sm font-medium hover:bg-secondary/80 transition-colors">
                  View Predictions
                </button>
                <button className="w-full bg-secondary text-secondary-foreground px-4 py-2 rounded-md text-sm font-medium hover:bg-secondary/80 transition-colors">
                  Resource Management
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  )
}
