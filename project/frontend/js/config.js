/**
 * Application Configuration
 */
const CONFIG = {
    API_BASE_URL: window.location.origin,
    WS_URL: `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/progress`,
    POLL_INTERVAL: 5000,
    TOAST_DURATION: 5000,
    DEFAULT_PAGE_SIZE: 20,
    DEFAULT_FRAME_PAGE_SIZE: 50,
    MAX_FILE_SIZE: 1024 * 1024 * 1024, // 1GB
    LOG_LEVEL: 'debug', // 'debug', 'info', 'warn', 'error'
    ENABLE_API_LOGGING: true,
    ENABLE_WS_LOGGING: true
};

// Initialize logger
if (typeof logger !== 'undefined') {
    logger.setLevel(CONFIG.LOG_LEVEL);
}

