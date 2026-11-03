/**
 * English translations
 */

export const en = {
  // Common
  common: {
    loading: 'Loading...',
    save: 'Save',
    cancel: 'Cancel',
    delete: 'Delete',
    add: 'Add',
    refresh: 'Refresh',
    close: 'Close',
    confirm: 'Confirm',
    error: 'Error',
    success: 'Success',
    unknown: 'Unknown',
    connected: 'Connected',
    disconnected: 'Disconnected',
    enabled: 'Enabled',
    disabled: 'Disabled',
    none: 'None',
    retry: 'Retry',
    test: 'Test',
    activate: 'Activate',
    activated: 'Activated',
    remove: 'Remove',
  },

  // Layout
  layout: {
    appTitle: 'AI Studio Proxy',
    chat: 'Chat',
    settings: 'Settings',
    modelSettings: 'Model Settings',
    logs: 'Logs',
    hideSettingsPanel: 'Hide Settings Panel',
    showSettingsPanel: 'Show Settings Panel',
    hideLogsPanel: 'Hide Logs Panel',
    showLogsPanel: 'Show Logs Panel',
    switchToLight: 'Switch to Light Mode',
    switchToDark: 'Switch to Dark Mode',
  },

  // Chat Panel
  chat: {
    startConversation: 'Start Conversation',
    startDescription: 'Type a message below to start chatting with the AI assistant',
    placeholder: 'Type a message... (Shift+Enter for new line)',
    clearChat: 'Clear Chat',
    stopGenerating: 'Stop Generating',
    sendMessage: 'Send Message',
    editMessage: 'Edit Message',
    regenerate: 'Regenerate',
    resend: 'Resend',
    thinking: 'Thinking...',
    thinkingProcess: 'Thinking Process',
    thinkingInterrupted: 'Thinking Interrupted',
    totalTime: 'Total Time',
    pausedResume: 'Log stream paused - click Play to resume',
    // Status messages
    connecting: 'Connecting...',
    thinkingStatus: 'Thinking...',
    generating: 'Generating...',
    regenerating: 'Regenerating...',
    generatingReply: 'Generating reply...',
    unknownError: 'An unknown error occurred',
  },

  // Settings Panel (Model Settings)
  settingsPanel: {
    modelSelection: 'Model Selection',
    currentModel: 'Current Model',
    refreshModelList: 'Refresh Model List',
    thinkingSettings: 'Thinking Settings',
    thinkingLevel: 'Thinking Level',
    thinkingMode: 'Thinking Mode',
    alwaysOnThinking: 'This model always has thinking enabled',
    enableThinking: 'Enable deep thinking capabilities',
    limitBudget: 'Limit Thinking Budget',
    limitBudgetDesc: 'Manually limit thinking tokens',
    thinkingBudget: 'Thinking Budget',
    noThinkingSupport: 'Current model does not support thinking configuration.',
    supportsLevels: 'supports {count} levels',
    unspecified: 'Unspecified',
    generationParams: 'Generation Parameters',
    temperature: 'Temperature',
    maxTokens: 'Max Tokens',
    topP: 'Top P',
    tools: 'Tools',
    googleSearch: 'Google Search',
    googleSearchDesc: 'Allow model to search web',
    googleSearchUnsupported: 'This model does not support Google Search',
    systemPrompt: 'System Prompt',
    systemPromptPlaceholder: 'Enter system prompt...',
  },

  // Settings Page
  settingsPage: {
    title: 'Server Settings',
    loading: 'Loading...',
    port: 'Port',
    
    // Status
    status: 'Status',
    uptime: 'Uptime',
    
    // API Keys
    apiKeys: 'API Keys',
    apiKeysDesc: 'Manage API keys for client authentication, allowing multiple applications to access the service.',
    noApiKeys: 'No API Keys',
    enterNewKey: 'Enter new API Key',
    keyAdded: 'API Key added',
    keyDeleted: 'API Key deleted',
    addFailed: 'Add failed',
    deleteFailed: 'Delete failed',
    confirmDelete: 'Are you sure you want to delete API Key: {key}...?',
    
    // Proxy
    proxySettings: 'Proxy Settings',
    proxyDesc: 'Configure HTTP/SOCKS5 proxy used for browser automation.',
    enableBrowserProxy: 'Enable Browser Proxy',
    enableBrowserProxyDesc: 'Route network traffic through proxy server',
    proxyAddress: 'Proxy Address',
    testConnection: 'Test Connection',
    saveConfig: 'Save',
    
    // Auth
    authManagement: 'Auth Management',
    authDesc: 'Manage saved authentication files and switch between accounts.',
    currentAuth: 'Current Auth',
    availableAuthFiles: 'Available Auth Files',
    noAuthFiles: 'No saved authentication files',
    activateAuth: 'Activate this auth',
    removeAuth: 'Remove Auth',
    
    // Ports
    portConfig: 'Port Configuration',
    portDesc: 'Configure service ports. Changes take effect after restart.',
    restartWarning: 'Changes will take effect after service restart',
    fastapiPort: 'FastAPI Service Port',
    camoufoxPort: 'Camoufox Debug Port',
    streamProxy: 'Stream Proxy Service',
    streamProxyPort: 'Stream Proxy Port',
    portRangeError: 'Port must be between 1024-65535',
  },

  // Log Viewer
  logs: {
    waitingForLogs: 'Waiting for logs...',
    connectingToServer: 'Connecting to log server...',
    pauseStream: 'Pause log stream',
    resumeStream: 'Resume log stream',
    downloadLogs: 'Download Logs',
    clearLogs: 'Clear Logs',
    pausedMessage: 'Log stream paused - click Play to resume',
  },

  // Error Boundary
  errors: {
    componentFailed: '{name} failed to load',
    unknownError: 'Unknown error',
  },

  // API Client errors
  api: {
    requestFailed: 'Request failed: {status}',
    networkError: 'Network error, please check connection',
    cannotReadStream: 'Cannot read response stream',
  },
} as const;
