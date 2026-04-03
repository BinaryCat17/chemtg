const { createApp, ref, computed, watch, nextTick, onMounted } = Vue;

const app = createApp({
    setup() {
        const sessions = ref([]);
        const activeSessionId = ref(null);
        const currentInput = ref('');
        const isLoading = ref(false);
        const messagesContainer = ref(null);

        // UI State
        const viewMode = ref('chat'); // 'chat' or 'browser'

        // Browser State
        const browserType = ref('pesticides');
        const browserSearch = ref('');
        const browserPage = ref(1);
        const browserData = ref({ items: [], total: 0 });
        let searchTimeout = null;

        // Product Detail State
        const selectedProduct = ref(null); // { type, info, applications }

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

        const formatDV = (dvJson) => {
            if (!dvJson) return '-';
            try {
                const data = typeof dvJson === 'string' ? JSON.parse(dvJson) : dvJson;
                if (Array.isArray(data)) {
                    return data.map(i => `${i.veshchestvo} (${i.koncentraciya} г/л)`).join(' + ');
                }
                return dvJson;
            } catch (e) { return dvJson; }
        };

        // Browser Logic
        const fetchBrowserData = async (page = 1) => {
            browserPage.value = page;
            const url = `/api/products/${browserType.value}?page=${page}&q=${encodeURIComponent(browserSearch.value)}`;
            try {
                const response = await fetch(url);
                if (response.ok) {
                    browserData.value = await response.json();
                }
            } catch (e) { console.error(e); }
        };

        const debouncedSearch = () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                fetchBrowserData(1);
            }, 500);
        };

        const openProductCard = async (item) => {
            const type = browserType.value === 'pesticides' ? 'pesticide' : 'agrochemical';
            const id = item.nomer_reg || item.Nomer_reg || item.rn || item.Rn;
            if (!id) {
                console.error("Could not find ID for item", item);
                return;
            }
            try {
                const response = await fetch(`/api/product/${type}/${id}`);
                if (response.ok) {
                    const data = await response.json();
                    selectedProduct.value = { type, ...data };
                }
            } catch (e) { console.error(e); }
        };

        const getItemKey = (item) => {
            return item.nomer_reg || item.Nomer_reg || item.rn || item.Rn || Math.random();
        };

        // Chat Link Handler
        const handleChatClick = (e) => {
            const target = e.target;
            // Если кликнули по ячейке таблицы или жирному тексту, пробуем найти это как препарат
            if (target.tagName === 'TD' || target.tagName === 'STRONG' || target.tagName === 'B') {
                const text = target.innerText.trim();
                if (text.length > 3) {
                    searchAndOpen(text);
                }
            }
        };

        const searchAndOpen = async (name) => {
            // Пробуем найти сначала в пестицидах
            try {
                const r1 = await fetch(`/api/products/pesticides?limit=1&q=${encodeURIComponent(name)}`);
                const d1 = await r1.json();
                if (d1.items.length > 0) {
                    openProductCardSpecific('pesticide', d1.items[0].nomer_reg);
                    return;
                }
                // Если не нашли, пробуем агрохимикаты
                const r2 = await fetch(`/api/products/agrochemicals?limit=1&q=${encodeURIComponent(name)}`);
                const d2 = await r2.json();
                if (d2.items.length > 0) {
                    openProductCardSpecific('agrochemical', d2.items[0].rn);
                    return;
                }
            } catch (e) { console.error(e); }
        };

        const openProductCardSpecific = async (type, id) => {
            try {
                const response = await fetch(`/api/product/${type}/${id}`);
                if (response.ok) {
                    const data = await response.json();
                    selectedProduct.value = { type, ...data };
                }
            } catch (e) { console.error(e); }
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
            
            if (app.config.globalProperties.$refs && app.config.globalProperties.$refs.inputField) {
                app.config.globalProperties.$refs.inputField.style.height = 'auto';
            }
            
            const session = sessions.value.find(s => s.id === activeSessionId.value);
            if (!session) return;

            if (session.messages.length === 0) {
                session.title = text;
            }

            const historyForApi = session.messages.map(m => ({
                role: m.role,
                content: m.content
            }));

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

                if (!response.ok) throw new Error('Ошибка API');
                const data = await response.json();
                session.messages.push({ role: 'assistant', content: data.answer });
            } catch (error) {
                console.error(error);
                session.messages.push({ role: 'assistant', content: '⚠️ Ошибка: ' + error.message });
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
            fetchBrowserData(); // Предзагрузка
        });

        watch(activeSessionId, () => {
            scrollToBottom();
        });

        return {
            sessions, activeSessionId, activeSession, currentInput, isLoading, messagesContainer,
            viewMode, browserType, browserSearch, browserPage, browserData, selectedProduct,
            dbStatus, vpnStatus, isUpdating,
            createNewSession, deleteSession, sendMessage, renderMarkdown, 
            adjustTextareaHeight, updateDatabase,
            fetchBrowserData, debouncedSearch, openProductCard, formatDV, handleChatClick,
            getItemKey
        };
    }
});

app.mount('#app');
