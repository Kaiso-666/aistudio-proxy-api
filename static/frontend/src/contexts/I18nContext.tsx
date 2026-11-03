/**
 * Internationalization (i18n) Context
 * Provides language switching between English and Chinese
 */

import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { en } from '@/i18n/en';
import { zh } from '@/i18n/zh';

export type Language = 'en' | 'zh';

// Use a looser type that allows both language files
type TranslationStrings = {
  common: {
    loading: string;
    save: string;
    cancel: string;
    delete: string;
    add: string;
    refresh: string;
    close: string;
    confirm: string;
    error: string;
    success: string;
    unknown: string;
    connected: string;
    disconnected: string;
    enabled: string;
    disabled: string;
    none: string;
    retry: string;
    test: string;
    activate: string;
    activated: string;
    remove: string;
  };
  layout: {
    appTitle: string;
    chat: string;
    settings: string;
    modelSettings: string;
    logs: string;
    hideSettingsPanel: string;
    showSettingsPanel: string;
    hideLogsPanel: string;
    showLogsPanel: string;
    switchToLight: string;
    switchToDark: string;
  };
  chat: {
    startConversation: string;
    startDescription: string;
    placeholder: string;
    clearChat: string;
    stopGenerating: string;
    sendMessage: string;
    editMessage: string;
    regenerate: string;
    resend: string;
    thinking: string;
    thinkingProcess: string;
    thinkingInterrupted: string;
    totalTime: string;
    pausedResume: string;
    connecting: string;
    thinkingStatus: string;
    generating: string;
    regenerating: string;
    generatingReply: string;
    unknownError: string;
  };
  settingsPanel: {
    modelSelection: string;
    currentModel: string;
    refreshModelList: string;
    thinkingSettings: string;
    thinkingLevel: string;
    thinkingMode: string;
    alwaysOnThinking: string;
    enableThinking: string;
    limitBudget: string;
    limitBudgetDesc: string;
    thinkingBudget: string;
    noThinkingSupport: string;
    supportsLevels: string;
    unspecified: string;
    generationParams: string;
    temperature: string;
    maxTokens: string;
    topP: string;
    tools: string;
    googleSearch: string;
    googleSearchDesc: string;
    googleSearchUnsupported: string;
    systemPrompt: string;
    systemPromptPlaceholder: string;
  };
  settingsPage: {
    title: string;
    loading: string;
    port: string;
    status: string;
    uptime: string;
    apiKeys: string;
    apiKeysDesc: string;
    noApiKeys: string;
    enterNewKey: string;
    keyAdded: string;
    keyDeleted: string;
    addFailed: string;
    deleteFailed: string;
    confirmDelete: string;
    proxySettings: string;
    proxyDesc: string;
    enableBrowserProxy: string;
    enableBrowserProxyDesc: string;
    proxyAddress: string;
    testConnection: string;
    saveConfig: string;
    authManagement: string;
    authDesc: string;
    currentAuth: string;
    availableAuthFiles: string;
    noAuthFiles: string;
    activateAuth: string;
    removeAuth: string;
    portConfig: string;
    portDesc: string;
    restartWarning: string;
    fastapiPort: string;
    camoufoxPort: string;
    streamProxy: string;
    streamProxyPort: string;
    portRangeError: string;
  };
  logs: {
    waitingForLogs: string;
    connectingToServer: string;
    pauseStream: string;
    resumeStream: string;
    downloadLogs: string;
    clearLogs: string;
    pausedMessage: string;
  };
  errors: {
    componentFailed: string;
    unknownError: string;
  };
  api: {
    requestFailed: string;
    networkError: string;
    cannotReadStream: string;
  };
};

interface I18nContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: TranslationStrings;
}

const I18nContext = createContext<I18nContextType | undefined>(undefined);

const STORAGE_KEY = 'ai-studio-proxy-language';

const translations: Record<Language, TranslationStrings> = {
  en: en as TranslationStrings,
  zh: zh as TranslationStrings,
};

function getInitialLanguage(): Language {
  if (typeof window === 'undefined') return 'en';
  
  // Check localStorage first
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'en' || stored === 'zh') {
    return stored;
  }
  
  // Check browser language
  const browserLang = navigator.language.toLowerCase();
  if (browserLang.startsWith('zh')) {
    return 'zh';
  }
  
  return 'en';
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(getInitialLanguage);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, language);
    document.documentElement.lang = language;
  }, [language]);

  const setLanguage = (lang: Language) => {
    setLanguageState(lang);
  };

  const value: I18nContextType = {
    language,
    setLanguage,
    t: translations[language],
  };

  return (
    <I18nContext.Provider value={value}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextType {
  const context = useContext(I18nContext);
  if (context === undefined) {
    throw new Error('useI18n must be used within an I18nProvider');
  }
  return context;
}
