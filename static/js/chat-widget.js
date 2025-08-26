class SupportChatWidget {
    constructor() {
        this.isOpen = false;
        this.sessionId = this.generateSessionId();
        this.escalated = false;
        this.adminConnected = false;
        
        this.initializeElements();
        this.bindEvents();
    }
    
    generateSessionId() {
        return 'chat_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
    }
    
    initializeElements() {
        this.chatToggle = document.getElementById('chat-toggle');
        this.chatWindow = document.getElementById('chat-window');
        this.chatMinimize = document.getElementById('chat-minimize');
        this.chatMessages = document.getElementById('chat-messages');
        this.chatInput = document.getElementById('chat-input');
        this.chatSend = document.getElementById('chat-send');
        this.escalationBanner = document.getElementById('escalation-banner');
        this.requestHuman = document.getElementById('request-human');
        this.chatBadge = document.getElementById('chat-badge');
    }
    
    bindEvents() {
        this.chatToggle.addEventListener('click', () => this.toggleChat());
        this.chatMinimize.addEventListener('click', () => this.toggleChat());
        this.chatSend.addEventListener('click', () => this.sendMessage());
        this.chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.sendMessage();
        });
        this.requestHuman.addEventListener('click', () => this.escalateToHuman());
    }
    
    toggleChat() {
        this.isOpen = !this.isOpen;
        this.chatWindow.style.display = this.isOpen ? 'flex' : 'none';
        
        if (this.isOpen) {
            this.chatInput.focus();
            this.hideBadge();
        }
        
        // Re-initialize feather icons for new elements
        if (typeof feather !== 'undefined') {
            feather.replace();
        }
    }
    
    showBadge(count = 1) {
        this.chatBadge.textContent = count;
        this.chatBadge.style.display = 'block';
    }
    
    hideBadge() {
        this.chatBadge.style.display = 'none';
    }
    
    async sendMessage() {
        const message = this.chatInput.value.trim();
        if (!message) return;
        
        // Add user message to chat
        this.addMessage(message, 'user');
        this.chatInput.value = '';
        
        // Show typing indicator
        this.showTypingIndicator();
        
        try {
            const response = await fetch('/api/chat/message', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    message: message
                })
            });
            
            const data = await response.json();
            
            this.hideTypingIndicator();
            
            if (data.success) {
                this.addMessage(data.response, 'ai');
                
                // Show escalation banner if AI suggests it
                if (data.should_escalate && !this.escalated) {
                    this.showEscalationBanner();
                }
                
                // Handle automatic escalation
                if (data.escalated) {
                    this.handleEscalation();
                }
            } else {
                this.addMessage('Sorry, I\'m having trouble right now. Let me get a human to help you.', 'ai');
                this.showEscalationBanner();
            }
        } catch (error) {
            this.hideTypingIndicator();
            this.addMessage('Connection error. Let me get a human to help you.', 'ai');
            this.showEscalationBanner();
        }
    }
    
    addMessage(content, sender, timestamp = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${sender}-message`;
        
        const timeStr = timestamp ? new Date(timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
        
        let senderName = '';
        if (sender === 'ai') senderName = 'AI Assistant';
        else if (sender === 'admin') senderName = 'Support Agent';
        else if (sender === 'user') senderName = 'You';
        
        messageDiv.innerHTML = `
            <div class="message-meta">
                <span class="sender-name">${senderName}</span>
                <span class="message-time">${timeStr}</span>
            </div>
            <div class="message-content">${this.escapeHtml(content)}</div>
        `;
        
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
        
        // Show badge if chat is closed and it's not a user message
        if (!this.isOpen && sender !== 'user') {
            this.showBadge();
        }
    }
    
    showTypingIndicator() {
        const typingDiv = document.createElement('div');
        typingDiv.className = 'chat-message ai-message typing-indicator';
        typingDiv.innerHTML = `
            <div class="message-content">
                <div class="typing-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        `;
        this.chatMessages.appendChild(typingDiv);
        this.scrollToBottom();
    }
    
    hideTypingIndicator() {
        const typingIndicator = this.chatMessages.querySelector('.typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }
    
    showEscalationBanner() {
        this.escalationBanner.style.display = 'block';
    }
    
    hideEscalationBanner() {
        this.escalationBanner.style.display = 'none';
    }
    
    async escalateToHuman() {
        try {
            const response = await fetch('/api/chat/escalate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: this.sessionId
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.handleEscalation();
            } else {
                this.addMessage('Unable to connect to human support right now. Please try again later.', 'ai');
            }
        } catch (error) {
            this.addMessage('Connection error. Please try again later.', 'ai');
        }
    }
    
    handleEscalation() {
        this.escalated = true;
        this.hideEscalationBanner();
        
        this.addMessage('🤝 I\'ve connected you with our support team. A human representative will be with you shortly.', 'system');
        
        // Start polling for human messages
        this.startPolling();
    }
    
    startPolling() {
        if (this.pollingInterval) return;
        
        this.pollingInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/chat/poll?session_id=${this.sessionId}`);
                const data = await response.json();
                
                if (data.success && data.messages) {
                    data.messages.forEach(msg => {
                        this.addMessage(msg.content, msg.sender_type, msg.created_at);
                    });
                }
                
                if (data.admin_connected && !this.adminConnected) {
                    this.adminConnected = true;
                    this.addMessage('👋 Hi! I\'m a human support agent. I can see your conversation history. How can I help you?', 'admin');
                }
            } catch (error) {
                console.error('Polling error:', error);
            }
        }, 3000); // Poll every 3 seconds
    }
    
    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize chat widget when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.supportChat = new SupportChatWidget();
});