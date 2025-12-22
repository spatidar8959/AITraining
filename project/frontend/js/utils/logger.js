/**
 * Logger Utility
 * Provides comprehensive logging for debugging with different log levels
 */
class Logger {
    constructor() {
        this.logs = [];
        this.maxLogs = 1000;
        this.enabled = true;
        this.logLevel = 'debug'; // 'debug', 'info', 'warn', 'error'
    }

    setLevel(level) {
        this.logLevel = level;
    }

    enable() {
        this.enabled = true;
    }

    disable() {
        this.enabled = false;
    }

    _shouldLog(level) {
        if (!this.enabled) return false;
        const levels = ['debug', 'info', 'warn', 'error'];
        return levels.indexOf(level) >= levels.indexOf(this.logLevel);
    }

    _addLog(level, category, message, data = null) {
        const logEntry = {
            timestamp: new Date().toISOString(),
            level,
            category,
            message,
            data: data ? JSON.parse(JSON.stringify(data)) : null
        };
        
        this.logs.push(logEntry);
        if (this.logs.length > this.maxLogs) {
            this.logs.shift();
        }

        return logEntry;
    }

    debug(category, message, data = null) {
        if (!this._shouldLog('debug')) return;
        const log = this._addLog('debug', category, message, data);
        console.debug(`[${log.timestamp}] [DEBUG] [${category}] ${message}`, data || '');
    }

    info(category, message, data = null) {
        if (!this._shouldLog('info')) return;
        const log = this._addLog('info', category, message, data);
        console.info(`[${log.timestamp}] [INFO] [${category}] ${message}`, data || '');
    }

    warn(category, message, data = null) {
        if (!this._shouldLog('warn')) return;
        const log = this._addLog('warn', category, message, data);
        console.warn(`[${log.timestamp}] [WARN] [${category}] ${message}`, data || '');
    }

    error(category, message, error = null) {
        if (!this._shouldLog('error')) return;
        const errorData = error ? {
            message: error.message,
            stack: error.stack,
            name: error.name
        } : null;
        const log = this._addLog('error', category, message, errorData);
        console.error(`[${log.timestamp}] [ERROR] [${category}] ${message}`, error || '');
    }

    api(method, endpoint, requestData = null, responseData = null, error = null) {
        const logData = {
            method,
            endpoint,
            request: requestData,
            response: responseData,
            error: error ? {
                message: error.message,
                stack: error.stack
            } : null,
            timestamp: new Date().toISOString()
        };

        if (error) {
            this.error('API', `${method} ${endpoint} - Failed`, logData);
        } else {
            this.info('API', `${method} ${endpoint} - Success`, logData);
        }
    }

    getLogs(level = null, category = null) {
        let filtered = this.logs;
        if (level) {
            filtered = filtered.filter(log => log.level === level);
        }
        if (category) {
            filtered = filtered.filter(log => log.category === category);
        }
        return filtered;
    }

    clearLogs() {
        this.logs = [];
    }

    exportLogs() {
        return JSON.stringify(this.logs, null, 2);
    }
}

// Global logger instance
const logger = new Logger();

