import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useState } from "react";

export function createControlCenterQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: false,
        staleTime: 5000,
        gcTime: 5 * 60 * 1000
      }
    }
  });
}

export const controlCenterQueryClient = createControlCenterQueryClient();

export function ControlCenterQueryProvider({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => createControlCenterQueryClient());
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
