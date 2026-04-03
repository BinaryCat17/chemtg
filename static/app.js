const { createApp, ref, computed, watch, nextTick, onMounted } = Vue;

const app = createApp({
    setup() {
        const sessions = ref([]);
        const activeSessionId = ref(null);
        const currentInput = ref('');
        const isLoading = ref(false);
        const messagesContainer = ref(null);

        // Status variables
        const dbStatus = ref({ connected: false, lastUpdate: '' });
        const vpnStatus = ref('Неизвестно');
        const isUpdating = ref(false);

        // Load from local storage
        const loadSessions = () => {
            const saved = localStorage.getItem('chemtg_sessions');
            if (saved) {
                sessions.value = JSON.parse(saved);
            }
            if (sessions.value.length === 0) {
                createNewSession();
            } else {
                activeSessionId.value = sessions.value[0].id;
            }
        };

        const saveSessions = () => {
            localStorage.setItem('chemtg_sessions', JSON.stringify(sessions.value));
        };

        const createNewSession = () => {
            const newId = Date.now().toString();
            sessions.value.unshift({
                id: newId,
                title: 'Новый диалог',
                messages: []
            });
            activeSessionId.value = newId;
            saveSessions();
        };

        const deleteSession = (id) => {
            if (confirm('Удалить этот диалог?')) {
                sessions.value = sessions.value.filter(s => s.id !== id);
                saveSessions();
                if (activeSessionId.value === id) {
                    if (sessions.value.length > 0) {
                        activeSessionId.value = sessions.value[0].id;
                    } else {
                        createNewSession();
                    }
                }
            }
        };

        const loadStatus = async () => {
            try {
                const response = await fetch('/api/status');
                if (response.ok) {
                    const data = await response.json();
                    dbStatus.value.connected = data.db_connected;
                    
                    if (data.db_last_update) {
                        const d = new Date(data.db_last_update + 'Z');
                        dbStatus.value.lastUpdate = d.toLocaleString('ru-RU', {
                            day: '2-digit', month: '2-digit', year: 'numeric', 
                            hour: '2-digit', minute: '2-digit'
                        });
                    } else {
                        dbStatus.value.lastUpdate = 'Нет данных';
                    }
                    vpnStatus.value = data.vpn_status;
                    isUpdating.value = data.is_updating || false;
                }
            } catch (e) {
                console.error('Failed to load status', e);
            }
        };

        const updateDatabase = async () => {
            if (isUpdating.value) return;
            if (!confirm('Запустить процесс обновления базы данных Минсельхоза? Это может занять несколько минут.')) return;
            
            isUpdating.value = true;
            try {
                const response = await fetch('/api/update_db', { method: 'POST' });
                if (!response.ok) {
                    alert('Ошибка при запуске обновления.');
                    isUpdating.value = false;
                } else {
                    // Refresh status immediately to ensure UI is in sync with the backend state
                    loadStatus();
                }
            } catch (e) {
                alert('Ошибка соединения с сервером.');
                isUpdating.value = false;
            }
        };

        const activeSession = computed(() => {
            return sessions.value.find(s => s.id === activeSessionId.value) || { messages: [] };
        });

        const scrollToBottom = async () => {
            await nextTick();
            if (messagesContainer.value) {
                messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
            }
        };

        // Render Markdown safely and wrap tables
        const renderMarkdown = (text) => {
            if (!text) return '';
            
            // Настроим marked, чтобы он оборачивал таблицы в div для прокрутки
            const renderer = new marked.Renderer();
            renderer.table = function(header, body) {
                return '<div class="table-container"><table><thead>' + header + '</thead><tbody>' + body + '</tbody></table></div>';
            };
            
            const html = marked.parse(text, { 
                renderer: renderer,
                breaks: true,
                gfm: true
            });
            return DOMPurify.sanitize(html);
        };

        const adjustTextareaHeight = (e) => {
            const target = e.target;
            target.style.height = 'auto';
            target.style.height = Math.min(target.scrollHeight, 200) + 'px';
        };

        const sendMessage = async () => {
            if (!currentInput.value.trim() || isLoading.value) return;

            const text = currentInput.value.trim();
            currentInput.value = '';
            
            // Сброс высоты
            if (app.config.globalProperties.$refs && app.config.globalProperties.$refs.inputField) {
                app.config.globalProperties.$refs.inputField.style.height = 'auto';
            }
            
            const session = sessions.value.find(s => s.id === activeSessionId.value);
            if (!session) return;

            // Set title if it's the first message
            if (session.messages.length === 0) {
                session.title = text;
            }

            // Extract history (excluding last user message as it will be sent separately or together)
            // But wait, agent.process_message expects history as list of dicts.
            const historyForApi = session.messages.map(m => ({
                role: m.role,
                content: m.content
            }));

            // Add user message to UI
            session.messages.push({ role: 'user', content: text });
            saveSessions();
            scrollToBottom();

            isLoading.value = true;

            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: text,
                        history: historyForApi,
                        session_id: session.id
                    })
                });

                if (!response.ok) {
                    throw new Error('Сетевая ошибка API сервера');
                }

                const data = await response.json();
                
                session.messages.push({ role: 'assistant', content: data.answer });
            } catch (error) {
                console.error(error);
                session.messages.push({ role: 'assistant', content: '⚠️ Произошла ошибка при связи с локальным сервером: ' + error.message });
            } finally {
                isLoading.value = false;
                saveSessions();
                scrollToBottom();
            }
        };

        onMounted(() => {
            loadSessions();
            scrollToBottom();
            loadStatus();
            setInterval(loadStatus, 30000);
        });

        watch(activeSessionId, () => {
            scrollToBottom();
        });

        return {
            sessions,
            activeSessionId,
            activeSession,
            currentInput,
            isLoading,
            messagesContainer,
            createNewSession,
            deleteSession,
            sendMessage,
            renderMarkdown,
            dbStatus,
            vpnStatus,
            isUpdating,
            updateDatabase
        };
    }
});

app.mount('#app');