/**
 * Auth Manager Component
 * Manage authentication profile files
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Key, Check, Trash2, RefreshCw, Loader2, AlertCircle } from 'lucide-react';
import { useI18n } from '@/contexts';
import { fetchAuthFiles, activateAuthFile, deactivateAuth } from '@/api';
import styles from './SettingsPanel.module.css';

export function AuthManager() {
  const { t } = useI18n();
  const queryClient = useQueryClient();

  // Fetch auth files
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['authFiles'],
    queryFn: fetchAuthFiles,
  });

  // Activate mutation
  const activateMutation = useMutation({
    mutationFn: activateAuthFile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['authFiles'] });
    },
  });

  // Deactivate mutation
  const deactivateMutation = useMutation({
    mutationFn: deactivateAuth,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['authFiles'] });
    },
  });

  const savedFiles = data?.saved_files || [];
  const activeFile = data?.active_file;

  if (isLoading) {
    return (
      <div className={styles.loading}>
        <Loader2 size={16} className={styles.spinning} />
        <span>{t.common.loading}</span>
      </div>
    );
  }

  return (
    <div className={styles.authManager}>
      {/* Current Active Auth */}
      <div className={styles.formGroup}>
        <label className={styles.label}>{t.settingsPage.currentAuth}</label>
        <div className={styles.activeAuthDisplay}>
          <Key size={14} />
          <span>{activeFile || t.common.none}</span>
        </div>
      </div>

      {/* Auth File List */}
      <div className={styles.formGroup}>
        <label className={styles.label}>{t.settingsPage.availableAuthFiles}</label>
        {savedFiles.length === 0 ? (
          <div className={styles.infoBox}>
            <AlertCircle size={16} />
            <span>{t.settingsPage.noAuthFiles}</span>
          </div>
        ) : (
          <div className={styles.authFileList}>
            {savedFiles.map((file) => (
              <div
                key={file.name}
                className={`${styles.authFileItem} ${file.is_active ? styles.active : ''}`}
              >
                <span className={styles.fileName}>{file.name}</span>
                <span className={styles.fileSize}>
                  {(file.size_bytes / 1024).toFixed(1)} KB
                </span>
                {!file.is_active && (
                  <button
                    className={styles.iconButton}
                    onClick={() => activateMutation.mutate(file.name)}
                    disabled={activateMutation.isPending}
                    title={t.settingsPage.activateAuth}
                  >
                    <Check size={14} />
                  </button>
                )}
                {file.is_active && (
                  <span className={styles.activeLabel}>{t.common.activated}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className={styles.buttonGroup}>
        <button
          className={styles.secondaryButton}
          onClick={() => refetch()}
          disabled={isLoading}
        >
          <RefreshCw size={14} />
          {t.common.refresh}
        </button>
        {activeFile && (
          <button
            className={styles.dangerButton}
            onClick={() => deactivateMutation.mutate()}
            disabled={deactivateMutation.isPending}
          >
            {deactivateMutation.isPending ? (
              <Loader2 size={14} className={styles.spinning} />
            ) : (
              <Trash2 size={14} />
            )}
            {t.settingsPage.removeAuth}
          </button>
        )}
      </div>
    </div>
  );
}
