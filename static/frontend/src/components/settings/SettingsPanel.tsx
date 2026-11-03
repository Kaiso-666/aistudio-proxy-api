/**
 * Settings Panel Component
 * Model settings and parameters with DYNAMIC thinking controls from backend API
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RefreshCw, ChevronDown, ChevronRight, AlertCircle, Loader2 } from 'lucide-react';
import { useSettings, useI18n } from '@/contexts';
import { fetchModels } from '@/api';
import { useModelCapabilities } from '@/hooks/useModelCapabilities';
import type { ThinkingLevel } from '@/types';
import styles from './SettingsPanel.module.css';

export function SettingsPanel() {
  const { t } = useI18n();
  const { settings, dispatch, selectedModel, setSelectedModel } = useSettings();
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    model: true,
    thinking: true,
    params: true,
    tools: true,
    system: false,
  });
  
  // Fetch models
  const { data: modelsData, isLoading: modelsLoading, refetch } = useQuery({
    queryKey: ['models'],
    queryFn: fetchModels,
    staleTime: 60000,
  });

  // Fetch model capabilities from backend (single source of truth)
  const { 
    getModelCategory, 
    getModelCapabilities, 
    isLoading: capabilitiesLoading 
  } = useModelCapabilities();

  const models = modelsData?.data || [];
  const category = getModelCategory(selectedModel);
  const capabilities = getModelCapabilities(selectedModel);

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  // Build thinking level options from capabilities
  const buildLevelOptions = (): { value: ThinkingLevel | ''; label: string }[] => {
    if (capabilities?.thinkingType !== 'level' || !capabilities.levels) {
      return [];
    }
    
    const options: { value: ThinkingLevel | ''; label: string }[] = [
      { value: '', label: t.settingsPanel.unspecified }
    ];
    
    for (const level of capabilities.levels) {
      options.push({ 
        value: level as ThinkingLevel, 
        label: level.charAt(0).toUpperCase() + level.slice(1) 
      });
    }
    
    return options;
  };

  const levelOptions = buildLevelOptions();

  // Get budget slider range from capabilities
  const getBudgetRange = () => {
    if (capabilities?.budgetRange) {
      return { min: capabilities.budgetRange[0], max: capabilities.budgetRange[1] };
    }
    return { min: 512, max: 24576 };
  };

  return (
    <div className={styles.settingsPanel}>
      {/* Model Selection */}
      <CollapsibleSection 
        title={t.settingsPanel.modelSelection} 
        expanded={expandedSections.model}
        onToggle={() => toggleSection('model')}
      >
        <div className={styles.formGroup}>
          <label className={styles.label}>{t.settingsPanel.currentModel}</label>
          <select
            className={styles.select}
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            disabled={modelsLoading}
            aria-label={t.settingsPanel.currentModel}
          >
            {models.length === 0 && (
              <option value="">{t.common.loading}</option>
            )}
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.id}
              </option>
            ))}
          </select>
        </div>
        <button 
          className={styles.refreshButton}
          onClick={() => refetch()}
          aria-label={t.settingsPanel.refreshModelList}
        >
          <RefreshCw size={14} aria-hidden="true" />
          {t.settingsPanel.refreshModelList}
        </button>
      </CollapsibleSection>

      {/* Thinking Settings - Dynamic UI based on backend capabilities */}
      <CollapsibleSection 
        title={t.settingsPanel.thinkingSettings} 
        expanded={expandedSections.thinking}
        onToggle={() => toggleSection('thinking')}
      >
        {capabilitiesLoading ? (
          <div className={styles.loading}>
            <Loader2 size={16} className={styles.spinning} />
            <span>{t.common.loading}</span>
          </div>
        ) : capabilities?.thinkingType === 'level' ? (
          /* Level selector (Gemini 3) */
          <div className={styles.formGroup}>
            <label className={styles.label}>{t.settingsPanel.thinkingLevel}</label>
            <select
              className={styles.select}
              value={settings.thinkingLevel}
              onChange={(e) => 
                dispatch({ type: 'SET_THINKING_LEVEL', payload: e.target.value })
              }
              aria-label={t.settingsPanel.thinkingLevel}
            >
              {levelOptions.map((level) => (
                <option key={level.value} value={level.value}>
                  {level.label}
                </option>
              ))}
            </select>
            <span className={styles.description}>
              {category} {t.settingsPanel.supportsLevels.replace('{count}', String(capabilities.levels?.length || 0))}
            </span>
          </div>
        ) : capabilities?.thinkingType === 'budget' ? (
          /* Budget controls (Gemini 2.5) */
          <>
            <Toggle
              label={t.settingsPanel.thinkingMode}
              description={capabilities.alwaysOn 
                ? t.settingsPanel.alwaysOnThinking 
                : t.settingsPanel.enableThinking
              }
              checked={capabilities.alwaysOn ? true : settings.enableThinking}
              disabled={capabilities.alwaysOn}
              onChange={(checked) => 
                dispatch({ type: 'SET_ENABLE_THINKING', payload: checked })
              }
            />
            {(capabilities.alwaysOn || settings.enableThinking) && (
              <>
                <Toggle
                  label={t.settingsPanel.limitBudget}
                  description={t.settingsPanel.limitBudgetDesc}
                  checked={settings.enableManualBudget}
                  onChange={(checked) => 
                    dispatch({ type: 'SET_ENABLE_MANUAL_BUDGET', payload: checked })
                  }
                />
                {settings.enableManualBudget && (
                  <Slider
                    label={t.settingsPanel.thinkingBudget}
                    value={settings.thinkingBudget}
                    min={getBudgetRange().min}
                    max={getBudgetRange().max}
                    step={128}
                    onChange={(value) => 
                      dispatch({ type: 'SET_THINKING_BUDGET', payload: value })
                    }
                  />
                )}
              </>
            )}
          </>
        ) : (
          /* No thinking support */
          <div className={styles.infoBox}>
            <AlertCircle size={16} aria-hidden="true" />
            <span>{t.settingsPanel.noThinkingSupport}</span>
          </div>
        )}
      </CollapsibleSection>

      {/* Parameters */}
      <CollapsibleSection 
        title={t.settingsPanel.generationParams} 
        expanded={expandedSections.params}
        onToggle={() => toggleSection('params')}
      >
        <Slider
          label={t.settingsPanel.temperature}
          value={settings.temperature}
          min={0}
          max={2}
          step={0.01}
          onChange={(value) => 
            dispatch({ type: 'SET_TEMPERATURE', payload: value })
          }
        />
        <Slider
          label={t.settingsPanel.maxTokens}
          value={settings.maxOutputTokens}
          min={1}
          max={65536}
          step={1}
          onChange={(value) => 
            dispatch({ type: 'SET_MAX_TOKENS', payload: value })
          }
        />
        <Slider
          label={t.settingsPanel.topP}
          value={settings.topP}
          min={0}
          max={1}
          step={0.01}
          onChange={(value) => 
            dispatch({ type: 'SET_TOP_P', payload: value })
          }
        />
      </CollapsibleSection>

      {/* Tools */}
      <CollapsibleSection 
        title={t.settingsPanel.tools} 
        expanded={expandedSections.tools}
        onToggle={() => toggleSection('tools')}
      >
        <Toggle
          label={t.settingsPanel.googleSearch}
          description={capabilities?.supportsGoogleSearch === false 
            ? t.settingsPanel.googleSearchUnsupported 
            : t.settingsPanel.googleSearchDesc
          }
          checked={capabilities?.supportsGoogleSearch === false ? false : settings.enableGoogleSearch}
          disabled={capabilities?.supportsGoogleSearch === false}
          onChange={(checked) => 
            dispatch({ type: 'SET_ENABLE_GOOGLE_SEARCH', payload: checked })
          }
        />
      </CollapsibleSection>

      {/* System Prompt */}
      <CollapsibleSection 
        title={t.settingsPanel.systemPrompt} 
        expanded={expandedSections.system}
        onToggle={() => toggleSection('system')}
      >
        <textarea
          className={styles.textarea}
          value={settings.systemPrompt}
          onChange={(e) => 
            dispatch({ type: 'SET_SYSTEM_PROMPT', payload: e.target.value })
          }
          placeholder={t.settingsPanel.systemPromptPlaceholder}
          aria-label={t.settingsPanel.systemPrompt}
        />
      </CollapsibleSection>
    </div>
  );
}

// Collapsible Section Component
function CollapsibleSection({
  title,
  expanded,
  onToggle,
  children,
}: {
  title: string;
  expanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className={styles.section}>
      <button 
        className={styles.sectionHeader} 
        onClick={onToggle}
        aria-expanded={expanded}
      >
        {expanded ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}
        <span>{title}</span>
      </button>
      <div className={`${styles.sectionContent} ${expanded ? styles.expanded : ''}`}>
        {children}
      </div>
    </div>
  );
}

// Slider Component
function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className={styles.formGroup}>
      <label className={styles.label}>{label}</label>
      <div className={styles.sliderGroup}>
        <input
          type="range"
          className={styles.slider}
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          aria-label={label}
        />
        <input
          type="number"
          className={styles.sliderInput}
          value={step < 1 ? value.toFixed(2) : value}
          min={min}
          max={max}
          step={step}
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            if (!isNaN(v)) onChange(v);
          }}
          aria-label={`${label} value`}
        />
      </div>
    </div>
  );
}

// Toggle Component
function Toggle({
  label,
  description,
  checked,
  disabled = false,
  onChange,
}: {
  label: string;
  description?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className={`${styles.toggle} ${disabled ? styles.disabled : ''}`}>
      <div className={styles.toggleLabel}>
        <span className={styles.label}>{label}</span>
        {description && <span className={styles.description}>{description}</span>}
      </div>
      <button
        className={`${styles.switch} ${checked ? styles.active : ''}`}
        onClick={() => !disabled && onChange(!checked)}
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
      >
        <span className={styles.switchThumb} aria-hidden="true" />
      </button>
    </div>
  );
}
