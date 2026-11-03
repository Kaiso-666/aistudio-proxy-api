/**
 * Layout Component
 * Main application layout with tabbed sidebars and error boundaries
 */

import { useState } from 'react';
import { 
  PanelLeft, 
  PanelRight, 
  Moon, 
  Sun,
  Layers,
  Settings,
  MessageSquare,
  Languages
} from 'lucide-react';
import { useTheme, useI18n, type Language } from '@/contexts';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { SettingsPanel } from '@/components/settings/SettingsPanel';
import { SettingsPage } from '@/components/settings/SettingsPage';
import { LogViewer } from '@/components/logs/LogViewer';
import styles from './Layout.module.css';

type MainView = 'chat' | 'settings';

export function Layout() {
  const { theme, toggleTheme } = useTheme();
  const { language, setLanguage, t } = useI18n();
  const [leftSidebarOpen, setLeftSidebarOpen] = useState(true);
  const [rightSidebarOpen, setRightSidebarOpen] = useState(true);
  const [mainView, setMainView] = useState<MainView>('chat');

  const toggleLanguage = () => {
    const newLang: Language = language === 'en' ? 'zh' : 'en';
    setLanguage(newLang);
  };

  return (
    <div className={styles.layout}>
      {/* Left Sidebar - Model Settings (only visible in chat mode) */}
      {mainView === 'chat' && (
        <aside 
          className={`${styles.sidebar} ${!leftSidebarOpen ? styles.collapsed : ''}`}
          role="complementary"
          aria-label={t.layout.modelSettings}
        >
          <div className={styles.sidebarHeader}>
            <span className={styles.sidebarTitle}>{t.layout.modelSettings}</span>
          </div>
          <div className={styles.sidebarContent}>
            <ErrorBoundary name={t.layout.modelSettings}>
              <SettingsPanel />
            </ErrorBoundary>
          </div>
        </aside>
      )}

      {/* Main Content */}
      <main className={styles.main} role="main">
        {/* Header */}
        <header className={styles.header} role="banner">
          <div className={styles.headerLeft}>
            {mainView === 'chat' && (
              <button 
                className={styles.toggleButton}
                onClick={() => setLeftSidebarOpen(!leftSidebarOpen)}
                aria-label={leftSidebarOpen ? t.layout.hideSettingsPanel : t.layout.showSettingsPanel}
                aria-expanded={leftSidebarOpen}
              >
                <PanelLeft size={20} aria-hidden="true" />
              </button>
            )}
            <div className={styles.logo}>
              <Layers className={styles.logoIcon} size={24} aria-hidden="true" />
              <span className={styles.logoText}>{t.layout.appTitle}</span>
            </div>
          </div>
          <div className={styles.headerCenter}>
            <div className={styles.mainTabs}>
              <button
                className={`${styles.mainTab} ${mainView === 'chat' ? styles.active : ''}`}
                onClick={() => setMainView('chat')}
              >
                <MessageSquare size={16} />
                {t.layout.chat}
              </button>
              <button
                className={`${styles.mainTab} ${mainView === 'settings' ? styles.active : ''}`}
                onClick={() => setMainView('settings')}
              >
                <Settings size={16} />
                {t.layout.settings}
              </button>
            </div>
          </div>
          <div className={styles.headerRight}>
            {/* Language Toggle Button */}
            <button 
              className={styles.langToggle}
              onClick={toggleLanguage}
              aria-label={language === 'en' ? '切换到中文' : 'Switch to English'}
              title={language === 'en' ? '切换到中文' : 'Switch to English'}
            >
              <Languages size={18} aria-hidden="true" />
              <span className={styles.langLabel}>{language === 'en' ? 'EN' : '中'}</span>
            </button>
            <button 
              className={styles.toggleButton}
              onClick={toggleTheme}
              aria-label={theme === 'dark' ? t.layout.switchToLight : t.layout.switchToDark}
            >
              {theme === 'dark' ? <Sun size={20} aria-hidden="true" /> : <Moon size={20} aria-hidden="true" />}
            </button>
            {mainView === 'chat' && (
              <button 
                className={styles.toggleButton}
                onClick={() => setRightSidebarOpen(!rightSidebarOpen)}
                aria-label={rightSidebarOpen ? t.layout.hideLogsPanel : t.layout.showLogsPanel}
                aria-expanded={rightSidebarOpen}
              >
                <PanelRight size={20} aria-hidden="true" />
              </button>
            )}
          </div>
        </header>

        {/* Content Area */}
        <div className={styles.content}>
          {mainView === 'chat' ? (
            <div className={styles.chatArea}>
              <ErrorBoundary name={t.layout.chat}>
                <ChatPanel />
              </ErrorBoundary>
            </div>
          ) : (
            <div className={styles.settingsArea}>
              <ErrorBoundary name={t.layout.settings}>
                <SettingsPage />
              </ErrorBoundary>
            </div>
          )}
        </div>
      </main>

      {/* Right Sidebar - Logs (only visible in chat mode) */}
      {mainView === 'chat' && (
        <aside 
          className={`${styles.rightSidebar} ${!rightSidebarOpen ? styles.collapsed : ''}`}
          role="complementary"
          aria-label={t.layout.logs}
        >
          <div className={styles.sidebarHeader}>
            <span className={styles.sidebarTitle}>
              {t.layout.logs}
            </span>
          </div>
          <div className={styles.sidebarContent}>
            <ErrorBoundary name={t.layout.logs}>
              {rightSidebarOpen && <LogViewer />}
            </ErrorBoundary>
          </div>
        </aside>
      )}
    </div>
  );
}
