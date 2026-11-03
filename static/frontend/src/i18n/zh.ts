/**
 * Chinese translations (中文翻译)
 */

export const zh = {
  // Common
  common: {
    loading: '加载中...',
    save: '保存',
    cancel: '取消',
    delete: '删除',
    add: '添加',
    refresh: '刷新',
    close: '关闭',
    confirm: '确认',
    error: '错误',
    success: '成功',
    unknown: '未知',
    connected: '已连接',
    disconnected: '已断开',
    enabled: '已启用',
    disabled: '已禁用',
    none: '无',
    retry: '重试',
    test: '测试',
    activate: '激活',
    activated: '已激活',
    remove: '移除',
  },

  // Layout
  layout: {
    appTitle: 'AI Studio 代理',
    chat: '聊天',
    settings: '设置',
    modelSettings: '模型设置',
    logs: '日志',
    hideSettingsPanel: '隐藏设置面板',
    showSettingsPanel: '显示设置面板',
    hideLogsPanel: '隐藏日志面板',
    showLogsPanel: '显示日志面板',
    switchToLight: '切换到亮色模式',
    switchToDark: '切换到暗色模式',
  },

  // Chat Panel
  chat: {
    startConversation: '开始对话',
    startDescription: '在下方输入消息开始与 AI 助手聊天',
    placeholder: '输入消息... (Shift+Enter 换行)',
    clearChat: '清空聊天',
    stopGenerating: '停止生成',
    sendMessage: '发送消息',
    editMessage: '编辑消息',
    regenerate: '重新生成',
    resend: '重新发送',
    thinking: '思考中...',
    thinkingProcess: '思考过程',
    thinkingInterrupted: '思考中断',
    totalTime: '总耗时',
    pausedResume: '日志流已暂停 - 点击播放恢复',
    // Status messages
    connecting: '正在连接...',
    thinkingStatus: '正在思考...',
    generating: '正在生成...',
    regenerating: '正在重新生成...',
    generatingReply: '正在生成回复...',
    unknownError: '发生未知错误',
  },

  // Settings Panel (Model Settings)
  settingsPanel: {
    modelSelection: '模型选择',
    currentModel: '当前模型',
    refreshModelList: '刷新模型列表',
    thinkingSettings: '思考设置',
    thinkingLevel: '思考等级',
    thinkingMode: '思考模式',
    alwaysOnThinking: '此模型始终启用思考模式',
    enableThinking: '启用模型的深度思考能力',
    limitBudget: '限制思考预算',
    limitBudgetDesc: '手动限制模型思考的 token 数量',
    thinkingBudget: '思考预算',
    noThinkingSupport: '当前模型不支持思考模式配置。',
    supportsLevels: '支持 {count} 个等级',
    unspecified: '未指定',
    generationParams: '生成参数',
    temperature: '温度',
    maxTokens: '最大令牌数',
    topP: 'Top P',
    tools: '工具',
    googleSearch: 'Google 搜索',
    googleSearchDesc: '允许模型搜索网络信息',
    googleSearchUnsupported: '此模型不支持 Google 搜索',
    systemPrompt: '系统提示',
    systemPromptPlaceholder: '输入系统提示词...',
  },

  // Settings Page
  settingsPage: {
    title: '服务器设置',
    loading: '加载中...',
    port: '端口',
    
    // Status
    status: '状态',
    uptime: '运行时间',
    
    // API Keys
    apiKeys: 'API 密钥',
    apiKeysDesc: '管理客户端认证的 API 密钥，允许多个应用程序访问服务。',
    noApiKeys: '暂无 API 密钥',
    enterNewKey: '输入新的 API 密钥',
    keyAdded: 'API 密钥已添加',
    keyDeleted: 'API 密钥已删除',
    addFailed: '添加失败',
    deleteFailed: '删除失败',
    confirmDelete: '确定要删除 API 密钥: {key}... 吗？',
    
    // Proxy
    proxySettings: '代理设置',
    proxyDesc: '配置用于浏览器自动化的 HTTP/SOCKS5 代理。',
    enableBrowserProxy: '启用浏览器代理',
    enableBrowserProxyDesc: '通过代理服务器访问网络',
    proxyAddress: '代理地址',
    testConnection: '测试连接',
    saveConfig: '保存',
    
    // Auth
    authManagement: '认证管理',
    authDesc: '管理已保存的认证文件并切换账户。',
    currentAuth: '当前认证',
    availableAuthFiles: '可用认证文件',
    noAuthFiles: '没有保存的认证文件',
    activateAuth: '激活此认证',
    removeAuth: '移除认证',
    
    // Ports
    portConfig: '端口配置',
    portDesc: '配置服务端口。更改将在重启后生效。',
    restartWarning: '更改将在下次重启服务时生效',
    fastapiPort: 'FastAPI 服务端口',
    camoufoxPort: 'Camoufox 调试端口',
    streamProxy: '流式代理服务',
    streamProxyPort: '流式代理端口',
    portRangeError: '端口必须在 1024-65535 之间',
  },

  // Log Viewer
  logs: {
    waitingForLogs: '等待日志...',
    connectingToServer: '正在连接日志服务器...',
    pauseStream: '暂停日志流',
    resumeStream: '恢复日志流',
    downloadLogs: '下载日志',
    clearLogs: '清空日志',
    pausedMessage: '日志流已暂停 - 点击播放恢复',
  },

  // Error Boundary
  errors: {
    componentFailed: '{name} 加载失败',
    unknownError: '未知错误',
  },

  // API Client errors
  api: {
    requestFailed: '请求失败: {status}',
    networkError: '网络错误，请检查连接',
    cannotReadStream: '无法读取响应流',
  },
} as const;
