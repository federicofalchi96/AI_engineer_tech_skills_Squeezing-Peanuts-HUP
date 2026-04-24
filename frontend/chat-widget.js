/**
 * Chat Widget Web Component
 * Usage:
 *   <script src="chat-widget.js"></script>
 *   <chat-widget backend="http://localhost:8000"></chat-widget>
 * 
 * Self-contained, zero dependencies, embeddable on any website
 */

class ChatWidget extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
        this.backendUrl = this.getAttribute('backend') || 'http://localhost:8000';
        this.chatHistory = [];
        this.isLoading = false;
    }

    connectedCallback() {
        this.render();
        this.setupEventListeners();
    }

    render() {
        const template = `
            <style>
                :host {
                    --primary-color: #2563eb;
                    --primary-dark: #1d4ed8;
                    --bg-light: #f8fafc;
                    --text-primary: #1e293b;
                    --text-secondary: #64748b;
                    --border-color: #e2e8f0;
                }

                .widget-container {
                    display: flex;
                    flex-direction: column;
                    height: 500px;
                    width: 100%;
                    max-width: 400px;
                    background: white;
                    border-radius: 12px;
                    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    border: 1px solid var(--border-color);
                }

                .header {
                    background: linear-gradient(to right, var(--primary-color), var(--primary-dark));
                    color: white;
                    padding: 16px;
                    border-radius: 12px 12px 0 0;
                    font-weight: 600;
                    font-size: 14px;
                }

                .chat-area {
                    flex: 1;
                    overflow-y: auto;
                    padding: 16px;
                    space-y: 16px;
                }

                .message {
                    display: flex;
                    gap: 8px;
                    margin-bottom: 12px;
                    animation: slideIn 0.3s ease-out;
                }

                .message.user {
                    justify-content: flex-end;
                }

                .message.agent {
                    justify-content: flex-start;
                }

                .message-bubble {
                    max-width: 80%;
                    padding: 10px 12px;
                    border-radius: 10px;
                    font-size: 13px;
                    line-height: 1.4;
                    word-wrap: break-word;
                }

                .message.user .message-bubble {
                    background: var(--primary-color);
                    color: white;
                    border-bottom-right-radius: 4px;
                }

                .message.agent .message-bubble {
                    background: var(--bg-light);
                    color: var(--text-primary);
                    border-bottom-left-radius: 4px;
                }

                .message-meta {
                    font-size: 11px;
                    color: var(--text-secondary);
                    margin-top: 4px;
                }

                .badge {
                    display: inline-block;
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-size: 10px;
                    font-weight: 600;
                    margin-right: 6px;
                }

                .badge.SALES {
                    background: #dcfce7;
                    color: #166534;
                }

                .badge.FINANCE {
                    background: #f3e8ff;
                    color: #6b21a8;
                }

                .badge.GENERAL {
                    background: #dbeafe;
                    color: #1e40af;
                }

                .input-area {
                    border-top: 1px solid var(--border-color);
                    padding: 12px;
                    background: var(--bg-light);
                    border-radius: 0 0 12px 12px;
                }

                .input-form {
                    display: flex;
                    gap: 8px;
                }

                .input-form input {
                    flex: 1;
                    padding: 8px 12px;
                    border: 1px solid var(--border-color);
                    border-radius: 6px;
                    font-size: 13px;
                    font-family: inherit;
                    transition: border-color 0.2s;
                }

                .input-form input:focus {
                    outline: none;
                    border-color: var(--primary-color);
                    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.1);
                }

                .input-form button {
                    padding: 8px 16px;
                    background: var(--primary-color);
                    color: white;
                    border: none;
                    border-radius: 6px;
                    cursor: pointer;
                    font-weight: 600;
                    font-size: 13px;
                    transition: background 0.2s;
                }

                .input-form button:hover:not(:disabled) {
                    background: var(--primary-dark);
                }

                .input-form button:disabled {
                    opacity: 0.6;
                    cursor: not-allowed;
                }

                .error-box {
                    padding: 8px 12px;
                    background: #fee2e2;
                    color: #991b1b;
                    border-radius: 6px;
                    font-size: 12px;
                    margin-bottom: 8px;
                    display: none;
                }

                .error-box.show {
                    display: block;
                }

                .typing-indicator {
                    display: flex;
                    gap: 4px;
                    padding: 8px;
                }

                .typing-dot {
                    width: 6px;
                    height: 6px;
                    border-radius: 50%;
                    background: var(--text-secondary);
                    animation: bounce 1.4s infinite;
                }

                .typing-dot:nth-child(2) {
                    animation-delay: 0.2s;
                }

                .typing-dot:nth-child(3) {
                    animation-delay: 0.4s;
                }

                @keyframes slideIn {
                    from {
                        opacity: 0;
                        transform: translateY(10px);
                    }
                    to {
                        opacity: 1;
                        transform: translateY(0);
                    }
                }

                @keyframes bounce {
                    0%, 80%, 100% {
                        transform: translateY(0);
                        opacity: 1;
                    }
                    40% {
                        transform: translateY(-8px);
                        opacity: 0.7;
                    }
                }

                .message-content strong {
                    font-weight: 600;
                }

                .message-content em {
                    font-style: italic;
                }
            </style>

            <div class="widget-container">
                <div class="header">Squeezing Peanuts</div>
                <div class="chat-area" id="chat-area"></div>
                <div class="input-area">
                    <div class="error-box" id="error-box"></div>
                    <form class="input-form" id="input-form">
                        <input 
                            type="text" 
                            id="query-input" 
                            placeholder="Ask me..." 
                            autocomplete="off"
                        />
                        <button type="submit" id="send-btn">Send</button>
                    </form>
                </div>
            </div>
        `;

        this.shadowRoot.innerHTML = template;
    }

    setupEventListeners() {
        const form = this.shadowRoot.getElementById('input-form');
        const input = this.shadowRoot.getElementById('query-input');
        const chatArea = this.shadowRoot.getElementById('chat-area');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const query = input.value.trim();
            if (!query || this.isLoading) return;

            // User message
            this.addMessage('user', query, null);
            input.value = '';

            this.isLoading = true;
            this.shadowRoot.getElementById('send-btn').disabled = true;

            try {
                const response = await fetch(`${this.backendUrl}/chat`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query })
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const data = await response.json();
                
                // Agent message
                this.addMessage('agent', data.response, {
                    domain: data.domain,
                    used_db: data.used_db
                });

            } catch (err) {
                console.error('Widget error:', err);
                this.showError(`Error: ${err.message}`);
            } finally {
                this.isLoading = false;
                this.shadowRoot.getElementById('send-btn').disabled = false;
                input.focus();
            }
        });
    }

    addMessage(role, content, metadata) {
        const chatArea = this.shadowRoot.getElementById('chat-area');
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';
        bubble.innerHTML = this.parseMarkdown(content);

        msgDiv.appendChild(bubble);

        if (metadata && role === 'agent') {
            const metaDiv = document.createElement('div');
            metaDiv.className = 'message-meta';
            metaDiv.innerHTML = `
                <span class="badge ${metadata.domain}">${metadata.domain}</span>
                ${metadata.used_db ? '<span></span>' : ''}
            `;
            msgDiv.appendChild(metaDiv);
        }

        chatArea.appendChild(msgDiv);
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    parseMarkdown(text) {
        let html = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        html = html
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/\n/g, '<br>');

        return html;
    }

    showError(message) {
        const errorBox = this.shadowRoot.getElementById('error-box');
        errorBox.textContent = message;
        errorBox.classList.add('show');
    }
}

// Register the custom element
customElements.define('chat-widget', ChatWidget);