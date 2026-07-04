import { QueryClient } from '@tanstack/react-query'

// A module-level singleton so non-component code (the WebSocket connection
// manager) can patch the cache directly via setQueryData/invalidateQueries,
// not just components rendered under <QueryClientProvider>.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})
