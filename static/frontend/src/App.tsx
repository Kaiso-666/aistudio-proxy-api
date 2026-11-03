/**
 * Main App Component
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider, SettingsProvider, ChatProvider, I18nProvider } from '@/contexts';
import { Layout } from '@/components/layout/Layout';
import '@/styles/index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000, // 30 seconds
      retry: 2,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <SettingsProvider>
            <ChatProvider>
              <Layout />
            </ChatProvider>
          </SettingsProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>
  );
}

export default App;
