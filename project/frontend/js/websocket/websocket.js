/**
 * WebSocket Manager
 * Handles WebSocket connections with reconnection logic
 */
class WebSocketManager {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 2000;
        this.heartbeatInterval = null;
        this.handlers = new Map();
        this.isConnecting = false;
    }

    connect() {
        if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.OPEN)) {
            logger.debug('WebSocket', 'Already connected or connecting');
            return;
        }

        this.isConnecting = true;
        
        // Get client session ID and append to WebSocket URL
        const clientSessionId = state.get('clientSessionId');
        let wsUrl = CONFIG.WS_URL;
        if (clientSessionId) {
            const separator = wsUrl.includes('?') ? '&' : '?';
            wsUrl = `${wsUrl}${separator}client_session_id=${encodeURIComponent(clientSessionId)}`;
        }
        
        logger.info('WebSocket', 'Connecting...', { url: wsUrl, clientSessionId });

        try {
            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
                logger.info('WebSocket', 'Connected successfully');
                this.reconnectAttempts = 0;
                this.isConnecting = false;
                this.updateStatus(true);
                this.startHeartbeat();
            };

            this.ws.onmessage = (event) => {
                try {
                    // Handle non-JSON messages (like "pong" heartbeat response)
                    if (event.data === 'pong' || event.data === 'ping') {
                        if (CONFIG.ENABLE_WS_LOGGING) {
                            logger.debug('WebSocket', `Heartbeat: ${event.data}`);
                        }
                        return; // Don't try to parse as JSON
                    }
                    
                    const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
                    
                    if (CONFIG.ENABLE_WS_LOGGING) {
                        logger.debug('WebSocket', 'Message received', data);
                    }
                    
                    this.handleMessage(data);
                } catch (e) {
                    logger.error('WebSocket', 'Failed to parse message', e);
                }
            };

            this.ws.onclose = (event) => {
                logger.warn('WebSocket', 'Connection closed', {
                    code: event.code,
                    reason: event.reason,
                    wasClean: event.wasClean
                });
                this.isConnecting = false;
                this.updateStatus(false);
                this.stopHeartbeat();
                
                if (!event.wasClean) {
                    this.attemptReconnect();
                }
            };

            this.ws.onerror = (error) => {
                logger.error('WebSocket', 'Connection error', error);
                this.isConnecting = false;
                this.updateStatus(false);
            };
        } catch (e) {
            logger.error('WebSocket', 'Failed to create WebSocket connection', e);
            this.isConnecting = false;
            this.updateStatus(false);
        }
    }

    updateStatus(connected) {
        const indicator = document.getElementById('wsIndicator');
        const status = document.getElementById('wsStatus');
        
        if (indicator && status) {
            if (connected) {
                indicator.className = 'w-2 h-2 rounded-full bg-green-500 mr-2 pulse';
                status.textContent = 'Live updates active';
            } else {
                indicator.className = 'w-2 h-2 rounded-full bg-red-500 mr-2';
                status.textContent = 'Disconnected';
            }
        }
    }

    startHeartbeat() {
        this.stopHeartbeat();
        this.heartbeatInterval = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                try {
                    this.ws.send('ping');
                    logger.debug('WebSocket', 'Heartbeat sent');
                } catch (error) {
                    logger.error('WebSocket', 'Failed to send heartbeat', error);
                }
            }
        }, 30000);
    }

    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * this.reconnectAttempts;
            logger.info('WebSocket', `Reconnect attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${delay}ms`);
            setTimeout(() => this.connect(), delay);
        } else {
            logger.error('WebSocket', 'Max reconnection attempts reached');
        }
    }

    on(type, handler) {
        if (!this.handlers.has(type)) {
            this.handlers.set(type, []);
        }
        this.handlers.get(type).push(handler);
        logger.debug('WebSocket', `Handler registered for: ${type}`);
    }

    off(type, handler) {
        if (this.handlers.has(type)) {
            const handlers = this.handlers.get(type);
            const index = handlers.indexOf(handler);
            if (index > -1) {
                handlers.splice(index, 1);
                logger.debug('WebSocket', `Handler removed for: ${type}`);
            }
        }
    }

    handleMessage(data) {
        const handlers = this.handlers.get(data.type);
        if (handlers) {
            handlers.forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    logger.error('WebSocket', `Error in handler for ${data.type}`, error);
                }
            });
        } else {
            logger.debug('WebSocket', `No handlers for message type: ${data.type}`);
        }
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            try {
                const message = typeof data === 'string' ? data : JSON.stringify(data);
                this.ws.send(message);
                logger.debug('WebSocket', 'Message sent', data);
            } catch (error) {
                logger.error('WebSocket', 'Failed to send message', error);
            }
        } else {
            logger.warn('WebSocket', 'Cannot send message - connection not open');
        }
    }

    disconnect() {
        logger.info('WebSocket', 'Disconnecting...');
        this.stopHeartbeat();
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.isConnecting = false;
    }
}

// Global WebSocket manager instance
const wsManager = new WebSocketManager();

