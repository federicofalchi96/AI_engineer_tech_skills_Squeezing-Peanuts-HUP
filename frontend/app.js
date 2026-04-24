/**
 * A2UI Chat Client
 * Implements A2UI protocol: https://a2ui.org
 * 
 * A2UI spec:
 * - Client sends: { "query": string }
 * - Server responds: { "response": string, "domain": enum, "used_db": bool, "status": "OK" }
 * - Client renders: messages + metadata (domain, timestamp, db usage)
 */

class A2UIChatClient {
    constructor(config = {}) {
        // In Docker: use service name (backend:8000)
        // Locally: use localhost:8000
        // Via env var: use VITE_API_URL if available
        this.backendUrl = config.backendUrl || 
                         window.location.origin || 
                         'http://backend:8000';
        
        console.log('Backend URL:', this.backendUrl);
        
        this.chatContainer = document.getElementById('chat-container');
        this.form = document.getElementById('chat-form');
        this.input = document.getElementById('user-input');
        this.errorBox = document.getElementById('error-box');
        this.sendBtn = document.getElementById('send-btn');
        this.spinner = document.getElementById('spinner');
        
        this.chatHistory = [];
        this.isLoading = false;

        this.init();
        this.initializeCostDisplay();
    }

    init() {
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));
        this.input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                this.form.dispatchEvent(new Event('submit'));
            }
        });
    }

    async handleSubmit(e) {
        e.preventDefault();
        
        const query = this.input.value.trim();
        if (!query || this.isLoading) return;

        this.input.value = '';
        this.addMessageToUI('user', query, null);
        this.chatHistory.push({ role: 'user', content: query });
        
        this.setLoading(true);
        this.errorBox.classList.add('hidden');
        
        try {
            const response = await this.queryBackend(query);
            
            if (response.status === 'OK') {
                // Calcola il costo
                let costUsd = 0;
                try {
                    const costResult = await this.logCost(query, response.response, response.domain, response.used_db);
                    if (costResult) {
                        costUsd = costResult.cost_usd;
                    }
                } catch (err) {
                    console.warn('Cost logging failed:', err);
                }
                this.addMessageToUI('agent', response.response, {
                    domain: response.domain,
                    used_db: response.used_db,
                    cost_usd: costUsd,
                    timestamp: new Date().toLocaleTimeString('it-IT', { 
                        hour: '2-digit', 
                        minute: '2-digit' 
                    })
                });
                            
                this.chatHistory.push({
                    role: 'assistant',
                    content: response.response,
                    metadata: {
                        domain: response.domain,
                        used_db: response.used_db
                    }
                });
            } else {
                this.showError(`Server error: ${response.status}`);
            }
        } catch (err) {
            console.error('Query failed:', err);
            this.showError(`Connection error: ${err.message}`);
        } finally {
            this.setLoading(false);
            this.input.focus();
            await this.updateCostDisplay();
        }
    }

    async queryBackend(query) {
        /**
         * POST /chat
         * Request: { "query": string }
         * Response: { "response": string, "domain": SALES|FINANCE|GENERAL, "used_db": bool, "status": OK }
         */
        const url = `${this.backendUrl}/chat`;
        console.log('POST to:', url);
        
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return await response.json();
    }

    async logCost(query, response, domain, used_db) {
    /**
     * Chiama il backend per calcolare il costo
     */
        try {
            const url = `${this.backendUrl}/log-query`;
            const res = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query,
                    response,
                    domain,
                    used_db
                })
            });

            if (!res.ok) {
                console.warn('Cost log failed:', res.status);
                return null;
            }

            return await res.json();
        } catch (err) {
            console.warn('Cost logging error:', err);
            return null;
        }
    }

    addMessageToUI(role, content, metadata) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role === 'user' ? 'user-message' : 'agent-message'}`;
        messageDiv.style.marginBottom = '24px';

        // Stili inline per garantire che funzionino
        if (role === 'user') {
            messageDiv.style.justifyContent = 'flex-end';
        } else {
            messageDiv.style.justifyContent = 'flex-start';
        }

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.innerHTML = this.parseContent(content);

        // Stili inline diretti
        contentDiv.style.maxWidth = '75%';
        contentDiv.style.padding = '12px 16px';
        contentDiv.style.borderRadius = '12px';
        contentDiv.style.fontSize = '14px';
        contentDiv.style.lineHeight = '1.5';
        contentDiv.style.wordWrap = 'break-word';

        if (role === 'user') {
            contentDiv.style.background = '#2563eb';
            contentDiv.style.color = 'white';
            contentDiv.style.marginLeft = 'auto';
        } else {
            contentDiv.style.background = '#f1f5f9';
            contentDiv.style.color = '#1e293b';
            contentDiv.style.border = '1px solid #e2e8f0';
            contentDiv.style.marginRight = 'auto';
        }

        messageDiv.appendChild(contentDiv);

        if (metadata && role !== 'user') {
            const metaDiv = document.createElement('div');
            metaDiv.style.display = 'flex';
            metaDiv.style.gap = '12px';
            metaDiv.style.alignItems = 'center';
            metaDiv.style.marginTop = '8px';
            metaDiv.style.fontSize = '12px';
            metaDiv.style.color = '#64748b';
            metaDiv.style.marginLeft = '0px';

            // Domain badge with better styling
            const domainColor = {
                'SALES': { bg: '#dcfce7', text: '#166534' },
                'FINANCE': { bg: '#f3e8ff', text: '#6b21a8' },
                'GENERAL': { bg: '#dbeafe', text: '#1e40af' }
            };
            const colors = domainColor[metadata.domain] || domainColor['GENERAL'];

            const domainBadge = document.createElement('span');
            domainBadge.textContent = `${metadata.domain}`;
            domainBadge.style.backgroundColor = colors.bg;
            domainBadge.style.color = colors.text;
            domainBadge.style.padding = '4px 10px';
            domainBadge.style.borderRadius = '6px';
            domainBadge.style.fontSize = '12px';
            domainBadge.style.fontWeight = '600';
            metaDiv.appendChild(domainBadge);

            // DB indicator
            if (metadata.used_db) {
                const dbBadge = document.createElement('span');
                dbBadge.textContent = 'DB';
                dbBadge.style.color = '#666';
                dbBadge.style.fontSize = '12px';
                metaDiv.appendChild(dbBadge);
            }

            // Cost
            if (metadata.cost_usd) {
                const costSpan = document.createElement('span');
                costSpan.textContent = `$${metadata.cost_usd.toFixed(6)}`;
                costSpan.style.fontFamily = 'monospace';
                costSpan.style.color = '#10b981';
                costSpan.style.fontSize = '12px';
                metaDiv.appendChild(costSpan);
            }

            // Timestamp
            const timeSpan = document.createElement('span');
            timeSpan.textContent = `${metadata.timestamp}`;
            timeSpan.style.color = '#999';
            timeSpan.style.fontSize = '12px';
            metaDiv.appendChild(timeSpan);

            messageDiv.appendChild(metaDiv);
        }

        this.chatContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }

    parseContent(text) {
        let html = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        html = html
            .replace(/^## (.+?)$/gm, '<h2>$1</h2>')
            .replace(/^### (.+?)$/gm, '<h3>$1</h3>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/__(.+?)__/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/_(.+?)_/g, '<em>$1</em>')
            .replace(/\n/g, '<br>');

        return html;
    }

    scrollToBottom() {
        this.chatContainer.scrollTop = this.chatContainer.scrollHeight;
    }

    setLoading(isLoading) {
        this.isLoading = isLoading;
        this.spinner.classList.toggle('hidden', !isLoading);
        this.sendBtn.disabled = isLoading;
        this.input.disabled = isLoading;
    }

    showError(message) {
        this.errorBox.textContent = message;
        this.errorBox.classList.remove('hidden');
    }

    async updateCostDisplay() {
        /**
         * Fetch cost status and update UI
         */
        try {
            console.log('Fetching cost status from:', `${this.backendUrl}/cost-status`);

            const response = await fetch(`${this.backendUrl}/cost-status`);
            if (!response.ok) {
                console.warn('Cost status fetch failed:', response.status);
                return;
            }

            const costStatus = await response.json();
            console.log('Cost status received:', costStatus);

            // Show cost display
            const costDisplay = document.getElementById('cost-display');
            costDisplay.style.display = 'block';

            // Update cost text
            const costText = document.getElementById('cost-text');
            costText.textContent = `$${costStatus.total_cost.toFixed(6)} / $${costStatus.cap.toFixed(2)}`;

            // Update progress bar
            const costBar = document.getElementById('cost-bar');
            const percentage = costStatus.percentage;
            costBar.style.width = percentage + '%';

            // Change color based on threshold
            if (costStatus.exceeded) {
                costBar.style.backgroundColor = '#ef4444'; // Red
            } else if (costStatus.warning) {
                costBar.style.backgroundColor = '#f59e0b'; // Amber
            } else {
                costBar.style.backgroundColor = '#10b981'; // Green
            }

            // Show/hide warning message
            const costWarning = document.getElementById('cost-warning');
            if (costStatus.warning && !costStatus.exceeded) {
                costWarning.style.display = 'block';
                document.getElementById('cost-remaining').textContent = `$${costStatus.remaining.toFixed(6)}`;
            } else {
                costWarning.style.display = 'none';
            }

            // Show/hide exceeded message
            const costExceeded = document.getElementById('cost-exceeded');
            if (costStatus.exceeded) {
                costExceeded.style.display = 'block';
                this.sendBtn.disabled = true;
                this.input.disabled = true;
                this.showError('Session cost limit reached. No more queries allowed.');
            } else {
                costExceeded.style.display = 'none';
                if (!this.isLoading) {
                    this.sendBtn.disabled = false;
                    this.input.disabled = false;
                }
            }
        } catch (err) {
            console.warn('Cost display update failed:', err);
        }
    }

    async initializeCostDisplay() {
        /**
         * Initialize cost display on page load
         */
        await this.updateCostDisplay();
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    // Detect backend URL: if on localhost:3000, use localhost:8001 for backend
    let backendUrl = window.location.origin;
    if (window.location.hostname === 'localhost' && window.location.port === '3000') {
        backendUrl = 'http://localhost:8001';
    } else if (window.location.hostname === 'localhost' && !window.location.port) {
        backendUrl = 'http://localhost:8001';
    }

    const client = new A2UIChatClient({
        backendUrl: backendUrl
    });
});