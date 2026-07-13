/**
 * 智能问答助手 - 前端应用
 *
 * 功能：
 * 1. RAG 智能问答（流式/快速）
 * 2. 引用来源展示（citations）
 * 3. 反馈评价系统（点赞/不喜欢 + 结构化负反馈）
 * 4. 知识库管理（列表/上传文档）
 * 5. 多会话历史管理
 */

class SmartQAApp {
    constructor() {
        this.apiBaseUrl = '/api';
        this.currentMode = 'stream'; // 'quick' 或 'stream'
        this.sessionId = this.generateSessionId();
        this.isStreaming = false;
        this.currentChatHistory = [];
        this.chatHistories = this.loadChatHistories();
        this.isCurrentChatFromHistory = false;

        // 反馈相关
        this.feedbackTargetMessageId = null;
        this.feedbackTargetSessionId = null;
        this.feedbackTargetQuestion = '';
        this.feedbackTargetAnswer = '';
        this.feedbackTargetCitations = [];
        this.selectedFeedbackTags = [];
        this.feedbackTags = [];

        // 停止生成
        this.abortController = null;

        this.initializeElements();
        this.bindEvents();
        this.initMarkdown();
        this.updateUI();
        this.checkAndSetCentered();
        this.renderChatHistory();
        this.loadServerChatHistories();
        this.loadFeedbackTags();
    }

    // ==================== Markdown 配置 ====================

    initMarkdown() {
        const checkMarked = () => {
            if (typeof marked !== 'undefined') {
                try {
                    marked.setOptions({
                        breaks: true,
                        gfm: true,
                        headerIds: false,
                        mangle: false,
                    });
                    if (typeof hljs !== 'undefined') {
                        marked.setOptions({
                            highlight: (code, lang) => {
                                if (lang && hljs.getLanguage(lang)) {
                                    try {
                                        return hljs.highlight(code, { language: lang }).value;
                                    } catch (err) {
                                        console.error('代码高亮失败:', err);
                                    }
                                }
                                return code;
                            },
                        });
                    }
                } catch (e) {
                    console.error('Markdown 配置失败:', e);
                }
            } else {
                setTimeout(checkMarked, 100);
            }
        };
        checkMarked();
    }

    renderMarkdown(content) {
        if (!content) return '';
        if (typeof marked === 'undefined') {
            return this.escapeHtml(content);
        }
        try {
            return marked.parse(content);
        } catch (e) {
            console.error('Markdown 渲染失败:', e);
            return this.escapeHtml(content);
        }
    }

    highlightCodeBlocks(container) {
        if (typeof hljs !== 'undefined' && container) {
            try {
                container.querySelectorAll('pre code').forEach((block) => {
                    if (!block.classList.contains('hljs')) {
                        hljs.highlightElement(block);
                    }
                });
            } catch (e) {
                console.error('代码高亮失败:', e);
            }
        }
    }

    // ==================== 元素初始化 ====================

    initializeElements() {
        this.sidebar = document.querySelector('.sidebar');
        this.newChatBtn = document.getElementById('newChatBtn');
        this.kbManageBtn = document.getElementById('kbManageBtn');

        // 顶部工具栏
        this.toolbarBugBtn = document.getElementById('toolbarBugBtn');

        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.stopButton = document.getElementById('stopButton');
        this.toolsBtn = document.getElementById('toolsBtn');
        this.toolsMenu = document.getElementById('toolsMenu');
        this.uploadFileItem = document.getElementById('uploadFileItem');
        this.kbManageMenuItem = document.getElementById('kbManageMenuItem');
        this.fileInput = document.getElementById('fileInput');

        this.chatMessages = document.getElementById('chatMessages');
        this.loadingOverlay = document.getElementById('loadingOverlay');
        this.chatContainer = document.querySelector('.chat-container');
        this.welcomeScreen = document.getElementById('welcomeScreen');
        this.chatHistoryList = document.getElementById('chatHistoryList');
        this.notificationContainer = document.getElementById('notificationContainer');

        // 反馈弹窗
        this.feedbackModal = document.getElementById('feedbackModal');
        this.feedbackModalClose = document.getElementById('feedbackModalClose');
        this.feedbackTagsContainer = document.getElementById('feedbackTagsContainer');
        this.feedbackDescription = document.getElementById('feedbackDescription');
        this.feedbackCancelBtn = document.getElementById('feedbackCancelBtn');
        this.feedbackSubmitBtn = document.getElementById('feedbackSubmitBtn');
        this.charCount = document.getElementById('charCount');

        // 知识库弹窗
        this.kbModal = document.getElementById('kbModal');
        this.kbModalClose = document.getElementById('kbModalClose');
        this.kbSelect = document.getElementById('kbSelect');
        this.kbUploadBtn = document.getElementById('kbUploadBtn');
        this.kbListContainer = document.getElementById('kbListContainer');

        // Bug上报弹窗
        this.bugReportMenuItem = document.getElementById('bugReportMenuItem');
        this.bugModal = document.getElementById('bugModal');
        this.bugModalClose = document.getElementById('bugModalClose');
        this.bugCategory = document.getElementById('bugCategory');
        this.bugTitle = document.getElementById('bugTitle');
        this.bugContent = document.getElementById('bugContent');
        this.bugAttachmentBtn = document.getElementById('bugAttachmentBtn');
        this.bugAttachmentName = document.getElementById('bugAttachmentName');
        this.bugFileInput = document.getElementById('bugFileInput');
        this.bugCancelBtn = document.getElementById('bugCancelBtn');
        this.bugSubmitBtn = document.getElementById('bugSubmitBtn');

        this.checkAndSetCentered();
    }

    // ==================== 事件绑定 ====================

    bindEvents() {
        if (this.newChatBtn) {
            this.newChatBtn.addEventListener('click', () => this.newChat());
        }

        // 建议卡片
        document.querySelectorAll('.suggestion-card').forEach(card => {
            card.addEventListener('click', () => {
                const question = card.getAttribute('data-question');
                if (question && this.messageInput) {
                    this.messageInput.value = question;
                    this.sendMessage();
                }
            });
        });

        // 发送
        if (this.sendButton) {
            this.sendButton.addEventListener('click', () => this.sendMessage());
        }
        if (this.messageInput) {
            this.messageInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }

        // 停止生成
        if (this.stopButton) {
            this.stopButton.addEventListener('click', () => this.stopGeneration());
        }

        // 工具菜单
        if (this.toolsBtn) {
            this.toolsBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleToolsMenu();
            });
        }
        if (this.uploadFileItem) {
            this.uploadFileItem.addEventListener('click', async () => {
                this.closeToolsMenu();
                await this.openKbModal();
                // 选择文件上传需要先选知识库
                this.showNotification('请先选择知识库，再上传文件', 'info');
            });
        }
        if (this.kbManageMenuItem) {
            this.kbManageMenuItem.addEventListener('click', () => {
                this.closeToolsMenu();
                this.openKbModal();
            });
        }
        if (this.kbManageBtn) {
            this.kbManageBtn.addEventListener('click', () => this.openKbModal());
        }

        // Bug上报
        if (this.bugReportMenuItem) {
            this.bugReportMenuItem.addEventListener('click', () => {
                this.closeToolsMenu();
                this.openBugModal();
            });
        }
        if (this.toolbarBugBtn) {
            this.toolbarBugBtn.addEventListener('click', () => {
                this.openBugModal();
            });
        }
        if (this.bugModalClose) {
            this.bugModalClose.addEventListener('click', () => this.closeBugModal());
        }
        if (this.bugCancelBtn) {
            this.bugCancelBtn.addEventListener('click', () => this.closeBugModal());
        }
        if (this.bugSubmitBtn) {
            this.bugSubmitBtn.addEventListener('click', () => this.submitBug());
        }
        if (this.bugAttachmentBtn) {
            this.bugAttachmentBtn.addEventListener('click', () => {
                if (this.bugFileInput) this.bugFileInput.click();
            });
        }
        if (this.bugFileInput) {
            this.bugFileInput.addEventListener('change', (e) => this.handleBugFileSelect(e));
        }
        if (this.bugModal) {
            this.bugModal.addEventListener('click', (e) => {
                if (e.target === this.bugModal) this.closeBugModal();
            });
        }
        document.addEventListener('click', (e) => {
            if (this.toolsBtn && this.toolsMenu &&
                !this.toolsBtn.contains(e.target) && !this.toolsMenu.contains(e.target)) {
                this.closeToolsMenu();
            }
        });

        // 文件上传
        if (this.fileInput) {
            this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
        }

        // 知识库弹窗
        if (this.kbModalClose) {
            this.kbModalClose.addEventListener('click', () => this.closeKbModal());
        }
        if (this.kbUploadBtn) {
            this.kbUploadBtn.addEventListener('click', () => {
                if (!this.kbSelect.value) {
                    this.showNotification('请先选择知识库', 'warning');
                    return;
                }
                if (this.fileInput) {
                    this.fileInput.click();
                }
            });
        }

        // 反馈弹窗
        if (this.feedbackModalClose) {
            this.feedbackModalClose.addEventListener('click', () => this.closeFeedbackModal());
        }
        if (this.feedbackCancelBtn) {
            this.feedbackCancelBtn.addEventListener('click', () => this.closeFeedbackModal());
        }
        if (this.feedbackSubmitBtn) {
            this.feedbackSubmitBtn.addEventListener('click', () => this.submitFeedback());
        }
        if (this.feedbackDescription) {
            this.feedbackDescription.addEventListener('input', () => {
                const len = this.feedbackDescription.value.length;
                if (this.charCount) {
                    this.charCount.textContent = `${len}/1000`;
                }
            });
        }

        // 点击遮罩关闭弹窗
        if (this.feedbackModal) {
            this.feedbackModal.addEventListener('click', (e) => {
                if (e.target === this.feedbackModal) this.closeFeedbackModal();
            });
        }
        if (this.kbModal) {
            this.kbModal.addEventListener('click', (e) => {
                if (e.target === this.kbModal) this.closeKbModal();
            });
        }
    }

    toggleToolsMenu() {
        if (this.toolsMenu && this.toolsBtn) {
            const wrapper = this.toolsBtn.closest('.tools-btn-wrapper');
            if (wrapper) wrapper.classList.toggle('active');
        }
    }

    closeToolsMenu() {
        if (this.toolsMenu && this.toolsBtn) {
            const wrapper = this.toolsBtn.closest('.tools-btn-wrapper');
            if (wrapper) wrapper.classList.remove('active');
        }
    }

    // ==================== 会话管理 ====================

    newChat() {
        if (this.isStreaming) {
            this.stopGeneration();
        }

        if (this.currentChatHistory.length > 0) {
            if (this.isCurrentChatFromHistory) {
                this.updateCurrentChatHistory();
            } else {
                this.saveCurrentChat();
            }
        }

        this.isStreaming = false;
        if (this.messageInput) this.messageInput.value = '';
        this.currentChatHistory = [];
        this.isCurrentChatFromHistory = false;

        if (this.chatMessages) this.chatMessages.innerHTML = '';
        this.sessionId = this.generateSessionId();
        this.updateUI();
        this.checkAndSetCentered();
        this.renderChatHistory();
    }

    generateSessionId() {
        return 'session_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
    }

    loadChatHistories() {
        try {
            const stored = localStorage.getItem('chatHistories');
            return stored ? JSON.parse(stored) : [];
        } catch (e) {
            console.error('加载历史对话失败:', e);
            return [];
        }
    }

    saveChatHistories() {
        try {
            localStorage.setItem('chatHistories', JSON.stringify(this.chatHistories));
        } catch (e) {
            console.error('保存历史对话失败:', e);
        }
    }

    saveCurrentChat() {
        if (this.currentChatHistory.length === 0) return;
        const existingIndex = this.chatHistories.findIndex(h => h.id === this.sessionId);
        if (existingIndex !== -1) {
            this.updateCurrentChatHistory();
            return;
        }
        const firstUserMessage = this.currentChatHistory.find(msg => msg.type === 'user');
        const title = firstUserMessage
            ? (firstUserMessage.content.substring(0, 30) + (firstUserMessage.content.length > 30 ? '...' : ''))
            : '新对话';
        this.chatHistories.unshift({
            id: this.sessionId,
            title: title,
            messages: [...this.currentChatHistory],
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
        });
        if (this.chatHistories.length > 50) {
            this.chatHistories = this.chatHistories.slice(0, 50);
        }
        this.saveChatHistories();
    }

    updateCurrentChatHistory() {
        if (this.currentChatHistory.length === 0) return;
        const existingIndex = this.chatHistories.findIndex(h => h.id === this.sessionId);
        if (existingIndex === -1) {
            this.saveCurrentChat();
            return;
        }
        const history = this.chatHistories[existingIndex];
        history.messages = [...this.currentChatHistory];
        history.updatedAt = new Date().toISOString();
        const firstUserMessage = this.currentChatHistory.find(msg => msg.type === 'user');
        if (firstUserMessage) {
            const newTitle = firstUserMessage.content.substring(0, 30) + (firstUserMessage.content.length > 30 ? '...' : '');
            if (history.title !== newTitle) history.title = newTitle;
        }
        this.saveChatHistories();
    }

    async loadServerChatHistories() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/chat/sessions`);
            if (!response.ok) return;
            const data = await response.json();
            const sessions = data.sessions || [];
            if (sessions.length === 0) return;
            this.chatHistories = sessions.map(session => ({
                id: session.session_id,
                title: session.title || '新对话',
                messages: [],
                createdAt: session.created_at,
                updatedAt: session.updated_at,
                lastMessagePreview: session.last_message_preview || '',
                messageCount: session.message_count || 0,
            }));
            this.saveChatHistories();
            this.renderChatHistory();
        } catch (error) {
            console.warn('加载服务端历史对话失败:', error);
        }
    }

    renderChatHistory() {
        if (!this.chatHistoryList) return;
        this.chatHistoryList.innerHTML = '';
        if (this.chatHistories.length === 0) return;

        this.chatHistories.forEach((history) => {
            const historyItem = document.createElement('div');
            historyItem.className = 'history-item';
            historyItem.dataset.historyId = history.id;
            historyItem.innerHTML = `
                <div class="history-item-content">
                    <svg class="history-item-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M21 15a2 2 0 0 1-2 2H7L3 21V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <span class="history-item-title">${this.escapeHtml(history.title)}</span>
                </div>
                <button class="history-item-delete" data-history-id="${history.id}" title="删除">
                    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                </button>
            `;
            historyItem.addEventListener('click', (e) => {
                if (!e.target.closest('.history-item-delete')) {
                    this.loadChatHistory(history.id);
                }
            });
            const deleteBtn = historyItem.querySelector('.history-item-delete');
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.deleteChatHistory(history.id);
            });
            this.chatHistoryList.appendChild(historyItem);
        });
    }

    async loadChatHistory(historyId) {
        const history = this.chatHistories.find(h => h.id === historyId);
        if (!history) return;

        if (this.currentChatHistory.length > 0 && this.sessionId !== historyId) {
            if (this.isCurrentChatFromHistory) {
                this.updateCurrentChatHistory();
            } else {
                this.saveCurrentChat();
            }
        }

        try {
            const response = await fetch(`/api/chat/session/${historyId}`);
            if (response.ok) {
                const data = await response.json();
                const backendHistory = data.history || [];
                this.sessionId = history.id;
                this.isCurrentChatFromHistory = true;

                if (this.chatMessages) {
                    this.chatMessages.innerHTML = '';
                    if (backendHistory.length > 0) {
                        this.currentChatHistory = [];
                        backendHistory.forEach(msg => {
                            const messageType = msg.role === 'user' ? 'user' : 'assistant';
                            this.addMessage(messageType, msg.content, false, false);
                        });
                    } else {
                        this.currentChatHistory = [...history.messages];
                        history.messages.forEach(msg => {
                            this.addMessage(msg.type, msg.content, false, false);
                        });
                    }
                }
            } else {
                this.sessionId = history.id;
                this.currentChatHistory = [...history.messages];
                this.isCurrentChatFromHistory = true;
                if (this.chatMessages) {
                    this.chatMessages.innerHTML = '';
                    history.messages.forEach(msg => {
                        this.addMessage(msg.type, msg.content, false, false);
                    });
                }
            }
        } catch (error) {
            console.error('加载会话历史失败:', error);
            this.sessionId = history.id;
            this.currentChatHistory = [...history.messages];
            this.isCurrentChatFromHistory = true;
            if (this.chatMessages) {
                this.chatMessages.innerHTML = '';
                history.messages.forEach(msg => {
                    this.addMessage(msg.type, msg.content, false, false);
                });
            }
        }
        this.checkAndSetCentered();
        this.renderChatHistory();
    }

    async deleteChatHistory(historyId) {
        try {
            const response = await fetch('/api/chat/clear', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sessionId: historyId }),
            });
            if (!response.ok) throw new Error('清空会话失败');
            const result = await response.json();
            if (result.status === 'success') {
                this.chatHistories = this.chatHistories.filter(h => h.id !== historyId);
                this.saveChatHistories();
                this.renderChatHistory();
                if (this.sessionId === historyId) {
                    this.currentChatHistory = [];
                    if (this.chatMessages) this.chatMessages.innerHTML = '';
                    this.sessionId = this.generateSessionId();
                    this.checkAndSetCentered();
                }
                this.showNotification('会话已清空', 'success');
            } else {
                throw new Error(result.message || '清空会话失败');
            }
        } catch (error) {
            console.error('删除历史对话失败:', error);
            this.showNotification('删除失败: ' + error.message, 'error');
        }
    }

    // ==================== 消息发送 ====================

    async sendMessage() {
        let message = '';
        if (this.messageInput) {
            message = this.messageInput.value.trim();
        }
        if (!message) {
            this.showNotification('请输入消息内容', 'warning');
            return;
        }
        if (this.isStreaming) {
            this.showNotification('请等待当前对话完成', 'warning');
            return;
        }

        this.addMessage('user', message);
        if (this.messageInput) this.messageInput.value = '';

        this.isStreaming = true;
        this.updateUI();

        try {
            // 默认使用流式模式
            await this.sendStreamMessage(message);
        } catch (error) {
            console.error('发送消息失败:', error);
            this.addMessage('assistant', '抱歉，发送消息时出现错误：' + error.message);
        } finally {
            this.isStreaming = false;
            this.updateUI();
            if (this.isCurrentChatFromHistory && this.currentChatHistory.length > 0) {
                this.updateCurrentChatHistory();
                this.renderChatHistory();
            }
        }
    }

    async sendStreamMessage(message) {
        this.abortController = new AbortController();

        try {
            const response = await fetch(`${this.apiBaseUrl}/chat_stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ Id: this.sessionId, Question: message }),
                signal: this.abortController.signal,
            });

            if (!response.ok) {
                throw new Error(`HTTP错误: ${response.status}`);
            }

            const assistantMessageElement = this.addMessage('assistant', '', true);
            let fullResponse = '';
            let citations = [];
            let messageId = null;

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            try {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) {
                        this.handleStreamComplete(assistantMessageElement, fullResponse, citations, messageId);
                        break;
                    }

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (line.trim() === '') continue;

                        if (line.startsWith('id:') || line.startsWith('event:')) {
                            continue;
                        } else if (line.startsWith('data:')) {
                            const rawData = line.substring(5).trim();
                            if (rawData === '[DONE]') {
                                this.handleStreamComplete(assistantMessageElement, fullResponse, citations, messageId);
                                return;
                            }

                            try {
                                const sseMessage = JSON.parse(rawData);

                                if (sseMessage.type === 'retrieving') {
                                    // 显示"正在检索知识库..."状态
                                    this.updateLoadingStatus(assistantMessageElement, '正在检索知识库...');
                                } else if (sseMessage.type === 'search_results') {
                                    citations = sseMessage.data || [];
                                    this.renderCitations(assistantMessageElement, citations);
                                    this.updateLoadingStatus(assistantMessageElement, '正在生成回答...');
                                } else if (sseMessage.type === 'content') {
                                    const content = sseMessage.data || '';
                                    fullResponse += content;
                                    const messageContent = assistantMessageElement.querySelector('.message-content');
                                    if (messageContent) {
                                        messageContent.innerHTML = this.renderMarkdown(fullResponse);
                                        this.highlightCodeBlocks(messageContent);
                                        this.scrollToBottom();
                                    }
                                } else if (sseMessage.type === 'done') {
                                    if (sseMessage.data) {
                                        fullResponse = sseMessage.data.answer || fullResponse;
                                        citations = sseMessage.data.citations || citations;
                                        messageId = sseMessage.data.message_id || messageId;
                                    }
                                    this.handleStreamComplete(assistantMessageElement, fullResponse, citations, messageId);
                                    return;
                                } else if (sseMessage.type === 'error') {
                                    console.error('SSE错误:', sseMessage.data);
                                    const messageContent = assistantMessageElement.querySelector('.message-content');
                                    if (messageContent) {
                                        messageContent.innerHTML = this.renderMarkdown('错误: ' + (sseMessage.data || '未知错误'));
                                    }
                                    return;
                                }
                            } catch (e) {
                                console.log('JSON解析失败，兼容处理:', e.message);
                                if (rawData) {
                                    fullResponse += rawData;
                                    const messageContent = assistantMessageElement.querySelector('.message-content');
                                    if (messageContent) {
                                        messageContent.innerHTML = this.renderMarkdown(fullResponse);
                                        this.highlightCodeBlocks(messageContent);
                                        this.scrollToBottom();
                                    }
                                }
                            }
                        }
                    }
                }
            } finally {
                reader.releaseLock();
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                console.log('用户停止了生成');
            } else {
                throw error;
            }
        } finally {
            this.abortController = null;
        }
    }

    stopGeneration() {
        if (this.abortController) {
            this.abortController.abort();
        }
        this.isStreaming = false;
        this.updateUI();
    }

    // ==================== 消息渲染 ====================

    addMessage(type, content, isStreaming = false, saveToHistory = true) {
        const isFirstMessage = this.chatMessages && this.chatMessages.querySelectorAll('.message').length === 0;

        if (!isStreaming && saveToHistory && content) {
            this.currentChatHistory.push({
                type: type,
                content: content,
                timestamp: new Date().toISOString(),
            });
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}${isStreaming ? ' streaming' : ''}`;

        if (type === 'assistant') {
            const messageAvatar = document.createElement('div');
            messageAvatar.className = 'message-avatar';
            messageAvatar.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" fill="white"/>
                </svg>
            `;
            messageDiv.appendChild(messageAvatar);
        }

        const messageContentWrapper = document.createElement('div');
        messageContentWrapper.className = 'message-content-wrapper';

        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';

        if (type === 'assistant' && !isStreaming) {
            messageContent.innerHTML = this.renderMarkdown(content);
            this.highlightCodeBlocks(messageContent);
        } else {
            messageContent.textContent = content;
        }

        messageContentWrapper.appendChild(messageContent);
        messageDiv.appendChild(messageContentWrapper);

        if (this.chatMessages) {
            this.chatMessages.appendChild(messageDiv);
            if (isFirstMessage && this.chatContainer) {
                this.chatContainer.classList.remove('centered');
            }
            this.scrollToBottom();
        }

        return messageDiv;
    }

    addLoadingMessage(content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';

        const messageAvatar = document.createElement('div');
        messageAvatar.className = 'message-avatar';
        messageAvatar.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" fill="white"/>
            </svg>
        `;
        messageDiv.appendChild(messageAvatar);

        const messageContentWrapper = document.createElement('div');
        messageContentWrapper.className = 'message-content-wrapper';

        const messageContent = document.createElement('div');
        messageContent.className = 'message-content loading-message-content';
        messageContent.innerHTML = `<span class="loading-text">${content}</span><span class="loading-dots"><span></span><span></span><span></span></span>`;

        messageContentWrapper.appendChild(messageContent);
        messageDiv.appendChild(messageContentWrapper);

        if (this.chatMessages) {
            this.chatMessages.appendChild(messageDiv);
            const isFirstMessage = this.chatMessages.querySelectorAll('.message').length === 1;
            if (isFirstMessage && this.chatContainer) {
                this.chatContainer.classList.remove('centered');
            }
            this.scrollToBottom();
        }

        return messageDiv;
    }

    updateLoadingStatus(messageElement, status) {
        if (!messageElement) return;
        const messageContent = messageElement.querySelector('.message-content');
        if (messageContent) {
            messageContent.innerHTML = `<span class="loading-text">${status}</span><span class="loading-dots"><span></span><span></span><span></span></span>`;
            messageContent.classList.add('loading-message-content');
        }
    }

    renderCitations(messageElement, citations) {
        if (!messageElement || !citations || citations.length === 0) return;

        const messageContentWrapper = messageElement.querySelector('.message-content-wrapper');
        if (!messageContentWrapper) return;

        // 移除已有的引用区域
        const existingCitations = messageContentWrapper.querySelector('.citations-container');
        if (existingCitations) existingCitations.remove();

        const citationsContainer = document.createElement('div');
        citationsContainer.className = 'citations-container';

        const citationsHeader = document.createElement('div');
        citationsHeader.className = 'citations-header';
        citationsHeader.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M9 18V5L21 3V16M9 18C9 19.6569 7.65685 21 6 21C4.34315 21 3 19.6569 3 18C3 16.3431 4.34315 15 6 15C7.65685 15 9 16.3431 9 18ZM21 13C21 14.6569 19.6569 16 18 16C16.3431 16 15 14.6569 15 13C15 11.3431 16.3431 10 18 10C19.6569 10 21 11.3431 21 13Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span>引用来源（${citations.length}）</span>
        `;
        citationsContainer.appendChild(citationsHeader);

        const citationsList = document.createElement('div');
        citationsList.className = 'citations-list';

        citations.forEach(citation => {
            const citationItem = document.createElement('div');
            citationItem.className = 'citation-item';
            citationItem.innerHTML = `
                <div class="citation-index">${citation.index}</div>
                <div class="citation-body">
                    <div class="citation-document">${this.escapeHtml(citation.document || '未知文档')}</div>
                    <div class="citation-preview">${this.escapeHtml(citation.content_preview || '')}</div>
                    <div class="citation-meta">相似度: ${(citation.similarity * 100).toFixed(1)}% · ID: ${this.escapeHtml(citation.id || '')}</div>
                </div>
            `;
            citationsList.appendChild(citationItem);
        });

        citationsContainer.appendChild(citationsList);
        messageContentWrapper.appendChild(citationsContainer);
    }

    renderFeedbackButtons(messageElement, messageId, citations) {
        if (!messageElement || !messageId) return;

        const messageContentWrapper = messageElement.querySelector('.message-content-wrapper');
        if (!messageContentWrapper) return;

        // 移除已有的反馈区域
        const existingActions = messageContentWrapper.querySelector('.message-actions');
        if (existingActions) existingActions.remove();

        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'message-actions';
        actionsDiv.dataset.messageId = messageId;

        const chunkIds = citations ? citations.map(c => c.id).filter(id => id) : [];

        actionsDiv.innerHTML = `
            <button class="action-btn like-btn" data-rating="like" title="点赞">
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M7 22V11M2 13V20C2 21.1046 2.89543 22 4 22H17.4C18.9 22 20.2 20.9 20.4 19.4L21.3 13.4C21.5 11.9 20.3 10.5 18.8 10.5H14C13.4 10.5 13 10 13.1 9.4L13.6 6.4C13.8 5.4 13.2 4.3 12.3 3.9C11.3 3.5 10.2 3.9 9.6 4.8L7 9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                <span>赞</span>
            </button>
            <button class="action-btn dislike-btn" data-rating="dislike" title="不喜欢">
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M17 2V13M22 11V4C22 2.89543 21.1046 2 20 2H6.6C5.1 2 3.8 3.1 3.6 4.6L2.7 10.6C2.5 12.1 3.7 13.5 5.2 13.5H10C10.6 13.5 11 14 10.9 14.6L10.4 17.6C10.2 18.6 10.8 19.7 11.7 20.1C12.7 20.5 13.8 20.1 14.4 19.2L17 15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                <span>踩</span>
            </button>
            <button class="action-btn copy-btn" title="复制回答">
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2"/>
                    <path d="M5 15H4C2.89543 15 2 14.1046 2 13V4C2 2.89543 2.89543 2 4 2H13C14.1046 2 15 2.89543 15 4V5" stroke="currentColor" stroke-width="2"/>
                </svg>
            </button>
        `;

        // 绑定反馈按钮事件
        const likeBtn = actionsDiv.querySelector('.like-btn');
        const dislikeBtn = actionsDiv.querySelector('.dislike-btn');
        const copyBtn = actionsDiv.querySelector('.copy-btn');

        likeBtn.addEventListener('click', () => {
            this.openFeedbackModal(messageId, 'like', chunkIds);
        });
        dislikeBtn.addEventListener('click', () => {
            this.openFeedbackModal(messageId, 'dislike', chunkIds);
        });
        copyBtn.addEventListener('click', () => {
            const content = messageElement.querySelector('.message-content');
            if (content) {
                navigator.clipboard.writeText(content.textContent || '').then(() => {
                    this.showNotification('已复制到剪贴板', 'success');
                });
            }
        });

        messageContentWrapper.appendChild(actionsDiv);

        // 检查已有反馈状态
        this.checkExistingFeedback(messageId, actionsDiv);
    }

    async checkExistingFeedback(messageId, actionsDiv) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/feedback/message/${messageId}`);
            if (!response.ok) return;
            const data = await response.json();
            if (data.data) {
                const rating = data.data.rating;
                if (rating === 'like') {
                    actionsDiv.querySelector('.like-btn').classList.add('active');
                } else if (rating === 'dislike') {
                    actionsDiv.querySelector('.dislike-btn').classList.add('active');
                }
            }
        } catch (e) {
            // 忽略错误
        }
    }

    handleStreamComplete(messageElement, fullResponse, citations, messageId) {
        if (!messageElement) return;
        messageElement.classList.remove('streaming');

        const messageContent = messageElement.querySelector('.message-content');
        if (messageContent) {
            messageContent.classList.remove('loading-message-content');
            messageContent.innerHTML = this.renderMarkdown(fullResponse);
            this.highlightCodeBlocks(messageContent);
        }

        // 渲染引用来源
        if (citations && citations.length > 0) {
            this.renderCitations(messageElement, citations);
        }

        // 渲染反馈按钮
        if (messageId) {
            this.renderFeedbackButtons(messageElement, messageId, citations);
        }

        // 保存到历史
        if (fullResponse) {
            this.currentChatHistory.push({
                type: 'assistant',
                content: fullResponse,
                timestamp: new Date().toISOString(),
                messageId: messageId,
                citations: citations,
            });
            if (this.isCurrentChatFromHistory) {
                this.updateCurrentChatHistory();
                this.renderChatHistory();
            }
            this.loadServerChatHistories();
        }
    }

    checkAndSetCentered() {
        if (this.chatMessages && this.chatContainer) {
            const hasMessages = this.chatMessages.querySelectorAll('.message').length > 0;
            if (!hasMessages) {
                this.chatContainer.classList.add('centered');
                if (this.welcomeScreen) this.welcomeScreen.style.display = 'flex';
            } else {
                this.chatContainer.classList.remove('centered');
                if (this.welcomeScreen) this.welcomeScreen.style.display = 'none';
            }
        }
    }

    scrollToBottom() {
        if (this.chatMessages) {
            this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        }
    }

    // ==================== UI 更新 ====================

    updateUI() {
        if (this.sendButton) {
            this.sendButton.style.display = this.isStreaming ? 'none' : 'flex';
        }
        if (this.stopButton) {
            this.stopButton.style.display = this.isStreaming ? 'flex' : 'none';
        }
        if (this.messageInput) {
            this.messageInput.disabled = false; // 允许输入（不锁定）
            if (!this.isStreaming) {
                this.messageInput.focus();
            }
        }
    }

    // ==================== 反馈系统 ====================

    async loadFeedbackTags() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/feedback/tags`);
            if (!response.ok) return;
            const data = await response.json();
            this.feedbackTags = (data.data && data.data.tags) || [];
        } catch (e) {
            console.warn('加载反馈标签失败:', e);
        }
    }

    openFeedbackModal(messageId, rating, chunkIds) {
        this.feedbackTargetMessageId = messageId;
        this.feedbackTargetRating = rating;
        this.feedbackTargetChunkIds = chunkIds || [];

        // 获取消息内容
        const messageElement = document.querySelector(`.message-actions[data-message-id="${messageId}"]`)?.closest('.message');
        if (messageElement) {
            const content = messageElement.querySelector('.message-content');
            this.feedbackTargetAnswer = content ? content.textContent : '';
            // 获取问题（上一条用户消息）
            const prevMessage = messageElement.previousElementSibling;
            if (prevMessage && prevMessage.classList.contains('user')) {
                const userContent = prevMessage.querySelector('.message-content');
                this.feedbackTargetQuestion = userContent ? userContent.textContent : '';
            }
        }

        // 重置选中状态
        this.selectedFeedbackTags = [];
        if (this.feedbackDescription) {
            this.feedbackDescription.value = '';
            if (this.charCount) this.charCount.textContent = '0/1000';
        }

        // 渲染标签
        if (this.feedbackTagsContainer) {
            this.feedbackTagsContainer.innerHTML = '';
            this.feedbackTags.forEach(tag => {
                const tagEl = document.createElement('div');
                tagEl.className = 'feedback-tag';
                tagEl.textContent = tag;
                tagEl.addEventListener('click', () => {
                    tagEl.classList.toggle('selected');
                    if (tagEl.classList.contains('selected')) {
                        if (!this.selectedFeedbackTags.includes(tag)) {
                            this.selectedFeedbackTags.push(tag);
                        }
                    } else {
                        this.selectedFeedbackTags = this.selectedFeedbackTags.filter(t => t !== tag);
                    }
                });
                this.feedbackTagsContainer.appendChild(tagEl);
            });
        }

        // 更新弹窗标题
        const modalTitle = this.feedbackModal.querySelector('.modal-title');
        if (modalTitle) {
            modalTitle.textContent = rating === 'like' ? '感谢您的反馈' : '帮助我们改进';
        }

        // 赞 → 直接提交；不喜欢 → 显示结构化选项
        if (rating === 'like') {
            this.submitFeedback();
            return;
        }

        if (this.feedbackModal) {
            this.feedbackModal.style.display = 'flex';
        }
    }

    closeFeedbackModal() {
        if (this.feedbackModal) {
            this.feedbackModal.style.display = 'none';
        }
        this.feedbackTargetMessageId = null;
        this.selectedFeedbackTags = [];
    }

    async submitFeedback() {
        if (!this.feedbackTargetMessageId) {
            this.showNotification('反馈信息缺失', 'error');
            return;
        }

        const description = this.feedbackDescription ? this.feedbackDescription.value.trim() : '';

        try {
            const response = await fetch(`${this.apiBaseUrl}/feedback`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sessionId: this.sessionId,
                    messageId: this.feedbackTargetMessageId,
                    rating: this.feedbackTargetRating,
                    question: this.feedbackTargetQuestion || '',
                    answer: this.feedbackTargetAnswer || '',
                    feedbackTags: this.feedbackTargetRating === 'dislike' ? this.selectedFeedbackTags : [],
                    feedbackDescription: description,
                    chunkIds: this.feedbackTargetChunkIds || [],
                }),
            });

            if (!response.ok) {
                throw new Error(`HTTP错误: ${response.status}`);
            }

            const data = await response.json();
            if (data.status === 'success') {
                this.showNotification('反馈已提交，感谢您的帮助！', 'success');
                // 更新按钮状态
                const actionsDiv = document.querySelector(`.message-actions[data-message-id="${this.feedbackTargetMessageId}"]`);
                if (actionsDiv) {
                    if (this.feedbackTargetRating === 'like') {
                        actionsDiv.querySelector('.like-btn').classList.add('active');
                        actionsDiv.querySelector('.dislike-btn').classList.remove('active');
                    } else {
                        actionsDiv.querySelector('.dislike-btn').classList.add('active');
                        actionsDiv.querySelector('.like-btn').classList.remove('active');
                    }
                }
                this.closeFeedbackModal();
            } else {
                throw new Error(data.message || '提交失败');
            }
        } catch (error) {
            console.error('提交反馈失败:', error);
            this.showNotification('提交反馈失败: ' + error.message, 'error');
        }
    }

    // ==================== 知识库管理 ====================

    async openKbModal() {
        if (this.kbModal) {
            this.kbModal.style.display = 'flex';
        }
        await this.loadKnowledgeBases();
    }

    closeKbModal() {
        if (this.kbModal) {
            this.kbModal.style.display = 'none';
        }
    }

    async loadKnowledgeBases() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/knowledge-bases`);
            if (!response.ok) {
                throw new Error(`HTTP错误: ${response.status}`);
            }
            const data = await response.json();
            const kbs = data.data || [];

            // 填充下拉框
            if (this.kbSelect) {
                this.kbSelect.innerHTML = '<option value="">请选择知识库...</option>' +
                    kbs.map(kb => `<option value="${kb.id}">${this.escapeHtml(kb.name)}</option>`).join('');
            }

            // 渲染知识库列表
            if (this.kbListContainer) {
                this.kbListContainer.innerHTML = '';
                if (kbs.length === 0) {
                    this.kbListContainer.innerHTML = '<div class="empty-state">暂无知识库</div>';
                } else {
                    for (const kb of kbs) {
                        const kbItem = document.createElement('div');
                        kbItem.className = 'kb-item';
                        kbItem.innerHTML = `
                            <div class="kb-item-info">
                                <div class="kb-item-name">${this.escapeHtml(kb.name)}</div>
                                <div class="kb-item-id">ID: ${this.escapeHtml(kb.id)}</div>
                            </div>
                            <button class="btn btn-small" data-kb-id="${kb.id}">查看文档</button>
                        `;
                        kbItem.querySelector('button').addEventListener('click', () => {
                            this.viewKbDocuments(kb.id, kb.name);
                        });
                        this.kbListContainer.appendChild(kbItem);
                    }
                }
            }
        } catch (error) {
            console.error('加载知识库列表失败:', error);
            this.showNotification('加载知识库失败: ' + error.message, 'error');
        }
    }

    async viewKbDocuments(kbId, kbName) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/knowledge-bases/${kbId}/docs`);
            if (!response.ok) {
                throw new Error(`HTTP错误: ${response.status}`);
            }
            const data = await response.json();
            const docs = data.data || [];

            if (docs.length === 0) {
                this.showNotification(`知识库「${kbName}」中暂无文档`, 'info');
            } else {
                const docList = docs.map(d => `• ${d.name}`).join('\n');
                this.showNotification(`知识库「${kbName}」有 ${docs.length} 个文档:\n${docList}`, 'info');
            }
        } catch (error) {
            console.error('查看文档失败:', error);
            this.showNotification('查看文档失败: ' + error.message, 'error');
        }
    }

    handleFileSelect(event) {
        const file = event.target.files[0];
        if (file) {
            this.uploadFile(file);
        }
    }

    async uploadFile(file) {
        const kbId = this.kbSelect ? this.kbSelect.value : '';
        if (!kbId) {
            this.showNotification('请先选择知识库', 'warning');
            return;
        }

        const maxSize = 50 * 1024 * 1024;
        if (file.size > maxSize) {
            this.showNotification('文件大小不能超过50MB', 'error');
            return;
        }

        this.isStreaming = true;
        this.updateUI();
        this.showUploadOverlay(true, file.name);

        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('kb_id', kbId);
            formData.append('auto_parse', 'true');

            const response = await fetch(`${this.apiBaseUrl}/upload`, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error(`HTTP错误: ${response.status}`);
            }

            const data = await response.json();
            if ((data.code === 200 || data.message === 'success') && data.data) {
                this.showNotification(`${file.name} 上传成功`, 'success');
                this.addMessage('user', `上传文档: ${file.name}`);
                this.addMessage('assistant', `文档「${file.name}」已成功上传到知识库，系统将自动解析并建立索引。`);
            } else {
                throw new Error(data.message || '上传失败');
            }
        } catch (error) {
            console.error('文件上传失败:', error);
            this.showNotification('文件上传失败: ' + error.message, 'error');
        } finally {
            if (this.fileInput) this.fileInput.value = '';
            this.isStreaming = false;
            this.showUploadOverlay(false);
            this.updateUI();
        }
    }

    // ==================== Bug 上报 ====================

    openBugModal() {
        // 重置表单
        if (this.bugTitle) this.bugTitle.value = '';
        if (this.bugContent) this.bugContent.value = '';
        if (this.bugFileInput) this.bugFileInput.value = '';
        if (this.bugAttachmentName) this.bugAttachmentName.textContent = '未选择文件';
        this.bugAttachmentFile = null;

        // 尝试预填当前对话上下文
        this.bugContextQuery = '';
        this.bugContextAnswer = '';
        if (this.currentChatHistory && this.currentChatHistory.length > 0) {
            const lastAssistant = [...this.currentChatHistory].reverse().find(m => m.type === 'assistant');
            const lastUser = [...this.currentChatHistory].reverse().find(m => m.type === 'user');
            if (lastUser) this.bugContextQuery = lastUser.content || '';
            if (lastAssistant) this.bugContextAnswer = lastAssistant.content || '';
        }

        if (this.bugModal) {
            this.bugModal.style.display = 'flex';
        }
    }

    closeBugModal() {
        if (this.bugModal) {
            this.bugModal.style.display = 'none';
        }
        this.bugAttachmentFile = null;
    }

    handleBugFileSelect(event) {
        const file = event.target.files[0];
        if (!file) return;

        const maxSize = 20 * 1024 * 1024;
        if (file.size > maxSize) {
            this.showNotification('附件大小不能超过20MB', 'error');
            if (this.bugFileInput) this.bugFileInput.value = '';
            return;
        }

        this.bugAttachmentFile = file;
        if (this.bugAttachmentName) {
            this.bugAttachmentName.textContent = file.name;
        }
    }

    async submitBug() {
        const category = this.bugCategory ? this.bugCategory.value : '';
        const title = this.bugTitle ? this.bugTitle.value.trim() : '';
        const content = this.bugContent ? this.bugContent.value.trim() : '';

        if (!title) {
            this.showNotification('请填写Bug标题', 'warning');
            return;
        }
        if (!content) {
            this.showNotification('请填写Bug详细描述', 'warning');
            return;
        }

        const formData = new FormData();
        formData.append('reporter', 'anonymous');
        formData.append('category', category);
        formData.append('title', title);
        formData.append('content', content);
        formData.append('session_id', this.sessionId || '');
        formData.append('query', this.bugContextQuery || '');
        formData.append('answer', this.bugContextAnswer || '');
        if (this.bugAttachmentFile) {
            formData.append('attachment', this.bugAttachmentFile);
        }

        this.showUploadOverlay(true);
        const loadingText = this.loadingOverlay ? this.loadingOverlay.querySelector('.loading-text') : null;
        const loadingSubtext = this.loadingOverlay ? this.loadingOverlay.querySelector('.loading-subtext') : null;
        if (loadingText) loadingText.textContent = '正在提交Bug...';
        if (loadingSubtext) loadingSubtext.textContent = '请稍候';

        try {
            const response = await fetch(`${this.apiBaseUrl}/bug/report`, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error(`HTTP错误: ${response.status}`);
            }

            const data = await response.json();
            if (data.code === 200) {
                this.showNotification('Bug上报成功，感谢您的反馈！', 'success');
                this.closeBugModal();
            } else {
                throw new Error(data.message || data.detail || '提交失败');
            }
        } catch (error) {
            console.error('Bug上报失败:', error);
            this.showNotification('Bug上报失败: ' + error.message, 'error');
        } finally {
            this.showUploadOverlay(false);
            if (loadingText) loadingText.textContent = '正在处理...';
            if (loadingSubtext) loadingSubtext.textContent = '请稍候';
        }
    }

    // ==================== 通知 ====================

    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 20px;
            border-radius: 8px;
            color: white;
            font-weight: 500;
            z-index: 10000;
            animation: slideIn 0.3s ease;
            max-width: 400px;
            white-space: pre-line;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        `;
        const colors = {
            info: '#1a73e8',
            success: '#34a853',
            warning: '#fbbc04',
            error: '#ea4335',
        };
        notification.style.backgroundColor = colors[type] || colors.info;
        document.body.appendChild(notification);
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => {
                if (notification.parentNode) notification.parentNode.removeChild(notification);
            }, 300);
        }, 3000);
    }

    showUploadOverlay(show, fileName = '') {
        if (this.loadingOverlay) {
            if (show) {
                this.loadingOverlay.style.display = 'flex';
                const loadingText = this.loadingOverlay.querySelector('.loading-text');
                const loadingSubtext = this.loadingOverlay.querySelector('.loading-subtext');
                if (loadingText) loadingText.textContent = '正在上传文件...';
                if (loadingSubtext) loadingSubtext.textContent = fileName ? `上传: ${fileName}` : '请稍候';
                document.body.style.overflow = 'hidden';
            } else {
                this.loadingOverlay.style.display = 'none';
                document.body.style.overflow = '';
            }
        }
    }

    // ==================== 工具方法 ====================

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// CSS 动画
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(style);

document.addEventListener('DOMContentLoaded', () => {
    new SmartQAApp();
});
