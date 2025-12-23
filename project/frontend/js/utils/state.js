/**
 * State Manager
 * Manages application state with persistence
 */
class StateManager {
    constructor() {
        this.state = this.loadState();
        this.listeners = new Map();
        logger.info('State', 'State manager initialized', { stateKeys: Object.keys(this.state) });
    }

    loadState() {
        try {
            const saved = localStorage.getItem('appState');
            if (saved) {
                const parsed = JSON.parse(saved);
                if (parsed.selectedFrames) parsed.selectedFrames = new Set(parsed.selectedFrames);
                if (parsed.selectedPoints) parsed.selectedPoints = new Set(parsed.selectedPoints);
                
                // Convert arrays back to Maps
                if (parsed.activeExtractions && Array.isArray(parsed.activeExtractions)) {
                    parsed.activeExtractions = new Map(parsed.activeExtractions);
                }
                if (parsed.activeTrainings && Array.isArray(parsed.activeTrainings)) {
                    parsed.activeTrainings = new Map(parsed.activeTrainings);
                }
                
                logger.debug('State', 'Loaded state from localStorage', { keys: Object.keys(parsed) });
                return { ...this.getDefaultState(), ...parsed };
            }
        } catch (error) {
            logger.error('State', 'Failed to load state from localStorage', error);
        }
        logger.debug('State', 'Using default state');
        return this.getDefaultState();
    }

    getDefaultState() {
        return {
            currentSection: 'dashboard',
            currentVideoPage: 1,
            currentFramePage: 1,
            currentTrainingPage: 1,
            currentQdrantPage: 1,
            pageSize: CONFIG.DEFAULT_PAGE_SIZE,
            framePageSize: CONFIG.DEFAULT_FRAME_PAGE_SIZE,
            selectedVideoId: null,
            selectedFrames: new Set(),
            selectedPoints: new Set(),
            currentTrainingJobId: null,
            clientSessionId: this.getOrCreateClientSessionId(),
            filters: {
                videoStatus: null,
                videoCategory: null,
                frameStatus: null,
                trainingStatus: null
            },
            activeExtractions: new Map(),
            activeTrainings: new Map(),
            pollingIntervals: {}
        };
    }

    getOrCreateClientSessionId() {
        try {
            let sessionId = localStorage.getItem('client_session_id');
            if (!sessionId) {
                // Generate a UUID v4
                sessionId = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                    const r = Math.random() * 16 | 0;
                    const v = c === 'x' ? r : (r & 0x3 | 0x8);
                    return v.toString(16);
                });
                localStorage.setItem('client_session_id', sessionId);
                logger.info('State', 'Generated new client session ID', { sessionId });
            } else {
                logger.debug('State', 'Using existing client session ID', { sessionId });
            }
            return sessionId;
        } catch (error) {
            logger.error('State', 'Failed to get or create client session ID', error);
            // Fallback: generate a simple ID if localStorage fails
            return 'session-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        }
    }

    saveState() {
        try {
            const stateToSave = {
                ...this.state,
                selectedFrames: Array.from(this.state.selectedFrames),
                selectedPoints: Array.from(this.state.selectedPoints),
                activeExtractions: Array.from(this.state.activeExtractions),
                activeTrainings: Array.from(this.state.activeTrainings),
                pollingIntervals: {}
            };
            localStorage.setItem('appState', JSON.stringify(stateToSave));
            logger.debug('State', 'State saved to localStorage');
        } catch (error) {
            logger.error('State', 'Failed to save state to localStorage', error);
        }
    }

    get(key) {
        const value = key ? this.state[key] : this.state;
        logger.debug('State', `Get state: ${key}`, { value });
        return value;
    }

    set(key, value) {
        const oldValue = this.state[key];
        this.state[key] = value;
        this.saveState();
        this.notifyListeners(key, value);
        logger.debug('State', `Set state: ${key}`, { oldValue, newValue: value });
    }

    update(updates) {
        logger.debug('State', 'Updating state', { updates });
        Object.assign(this.state, updates);
        this.saveState();
        Object.keys(updates).forEach(key => {
            this.notifyListeners(key, updates[key]);
        });
    }

    clearPolling() {
        const count = Object.keys(this.state.pollingIntervals).length;
        Object.values(this.state.pollingIntervals).forEach(interval => clearInterval(interval));
        this.state.pollingIntervals = {};
        logger.debug('State', `Cleared ${count} polling intervals`);
    }

    on(key, listener) {
        if (!this.listeners.has(key)) {
            this.listeners.set(key, []);
        }
        this.listeners.get(key).push(listener);
        logger.debug('State', `Added listener for: ${key}`);
    }

    off(key, listener) {
        if (this.listeners.has(key)) {
            const listeners = this.listeners.get(key);
            const index = listeners.indexOf(listener);
            if (index > -1) {
                listeners.splice(index, 1);
                logger.debug('State', `Removed listener for: ${key}`);
            }
        }
    }

    notifyListeners(key, value) {
        const listeners = this.listeners.get(key);
        if (listeners) {
            listeners.forEach(listener => {
                try {
                    listener(value);
                } catch (error) {
                    logger.error('State', `Error in listener for ${key}`, error);
                }
            });
        }
    }
}

// Global state instance
const state = new StateManager();

