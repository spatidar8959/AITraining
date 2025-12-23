/**
 * Application Initialization
 * Main entry point for the application
 */
class App {
    static init() {
        logger.info('App', 'Initializing application');
        
        try {
            // Ensure client session ID is initialized
            const clientSessionId = state.get('clientSessionId');
            if (!clientSessionId) {
                state.set('clientSessionId', state.getOrCreateClientSessionId());
            }
            logger.info('App', 'Client session initialized', { clientSessionId: state.get('clientSessionId') });
            
            this.setupNav();
            this.registerRoutes();
            router.init();
            this.setupEvents();
            this.setupWebSocket();

            // Initial health check
            setTimeout(() => this.checkHealth(), 1000);
            
            logger.info('App', 'Application initialized successfully');
        } catch (error) {
            logger.error('App', 'Failed to initialize application', error);
            UI.handleError(error, 'Application initialization');
        }
    }

    static registerRoutes() {
        logger.debug('App', 'Registering routes');
        router.register('dashboard', () => Dashboard.render());
        router.register('videos', () => Videos.render());
        router.register('frames', (params) => Frames.render(params));
        router.register('training', () => Training.render());
        router.register('qdrant', () => Qdrant.render());
    }

    static setupNav() {
        const items = [
            { id: 'dashboard', icon: 'chart-bar', label: 'Dashboard' },
            { id: 'videos', icon: 'video', label: 'Videos' },
            { id: 'frames', icon: 'images', label: 'Frames' },
            { id: 'training', icon: 'brain', label: 'Training' },
            { id: 'qdrant', icon: 'database', label: 'Qdrant' }
        ];

        const navList = document.getElementById('navList');
        if (!navList) {
            logger.error('App', 'Navigation list element not found');
            return;
        }

        navList.innerHTML = items.map(i => `
            <li>
                <a href="#${i.id}" data-section="${i.id}" class="nav-link flex items-center p-3 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition-colors">
                    <i class="fas fa-${i.icon} mr-3"></i>
                    <span>${i.label}</span>
                </a>
            </li>
        `).join('');

        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                router.navigate(e.currentTarget.dataset.section);
            });
        });

        logger.debug('App', 'Navigation setup completed');
    }

    static setupEvents() {
        const mobileMenuBtn = document.getElementById('mobileMenuBtn');
        const healthCheckBtn = document.getElementById('healthCheckBtn');

        if (mobileMenuBtn) {
            mobileMenuBtn.addEventListener('click', () => {
                const sidebar = document.getElementById('sidebar');
                if (sidebar) {
                    sidebar.classList.toggle('active');
                }
            });
        }

        document.addEventListener('click', (e) => {
            const sidebar = document.getElementById('sidebar');
            const btn = document.getElementById('mobileMenuBtn');

            if (window.innerWidth < 1024 &&
                sidebar && btn &&
                !sidebar.contains(e.target) &&
                !btn.contains(e.target)) {
                sidebar.classList.remove('active');
            }
        });

        if (healthCheckBtn) {
            healthCheckBtn.addEventListener('click', () => {
                this.checkHealth();
            });
        }

        window.addEventListener('beforeunload', () => {
            state.clearPolling();
            wsManager.disconnect();
            logger.info('App', 'Application cleanup completed');
        });

        logger.debug('App', 'Event handlers setup completed');
    }

    static setupWebSocket() {
        logger.debug('App', 'Setting up WebSocket handlers');
        
        wsManager.connect();

        // Handle extraction progress
        wsManager.on('extraction_progress', (data) => {
            // Filter by client session ID - only process events for this client
            const currentSessionId = state.get('clientSessionId');
            if (data.client_session_id && data.client_session_id !== currentSessionId) {
                if (CONFIG.ENABLE_WS_LOGGING) {
                    logger.debug('App', 'Ignoring extraction progress for different session', {
                        received: data.client_session_id,
                        current: currentSessionId
                    });
                }
                return; // Ignore events from other sessions
            }

            if (CONFIG.ENABLE_WS_LOGGING) {
                logger.info('App', 'Extraction progress received', data);
            }
            
            UI.showToast(`Extraction: ${data.percent || 0}% (${data.current || 0}/${data.total || 0})`, 'info');

            if (data.status === 'completed') {
                UI.showToast('Frame extraction completed!', 'success');
                state.state.activeExtractions.delete(data.video_id);
                state.saveState();

                // Close any open modals and refresh
                document.querySelector('.modal-overlay')?.remove();

                // Auto-refresh if on relevant page
                if (router.current === 'videos' || router.current === 'dashboard') {
                    setTimeout(() => {
                        try {
                            if (router.current === 'videos' && typeof Videos !== 'undefined') {
                                Videos.load();
                            } else if (router.current === 'dashboard' && typeof Dashboard !== 'undefined') {
                                Dashboard.loadRecentVideos();
                                Dashboard.refreshStats(); // Add this to refresh stats
                            }
                        } catch (error) {
                            logger.error('App', 'Error refreshing page after extraction', error);
                        }
                    }, 1000);
                }
                
                // Auto-navigate to frames section if extraction was triggered from modal
                setTimeout(() => {
                    const videoId = data.video_id;
                    if (videoId) {
                        state.set('selectedVideoId', videoId);
                        router.navigate('frames', { videoId: videoId });
                    }
                }, 2000);
            }
        });

        // Handle training progress
        wsManager.on('training_progress', (data) => {
            // Filter by client session ID - only process events for this client
            const currentSessionId = state.get('clientSessionId');
            if (data.client_session_id && data.client_session_id !== currentSessionId) {
                if (CONFIG.ENABLE_WS_LOGGING) {
                    logger.debug('App', 'Ignoring training progress for different session', {
                        received: data.client_session_id,
                        current: currentSessionId
                    });
                }
                return; // Ignore events from other sessions
            }

            if (CONFIG.ENABLE_WS_LOGGING) {
                logger.info('App', 'Training progress received', data);
            }
            
            UI.showToast(`Training: ${data.percent || 0}% (${data.current || 0}/${data.total || 0})`, 'info');

            // Refresh frames periodically during training (every 25% progress)
            if (router.current === 'frames' && data.percent && data.percent % 25 === 0) {
                const videoId = state.get('selectedVideoId');
                if (videoId && typeof Frames !== 'undefined' && Frames.loadFrames) {
                    setTimeout(() => {
                        Frames.loadFrames(videoId);
                    }, 500);
                }
            }

            if (data.status === 'completed') {
                UI.showToast('Training completed!', 'success');
                state.state.activeTrainings.delete(data.job_id);
                state.saveState();
                
                // Refresh training page if on training page
                if (router.current === 'training') {
                    setTimeout(() => {
                        try {
                            if (typeof Training !== 'undefined' && Training.load) {
                                logger.info('App', 'Refreshing training page after completion');
                                Training.load();
                            }
                        } catch (error) {
                            logger.error('App', 'Error refreshing training page', error);
                        }
                    }, 1000);
                }
                
                // Refresh frames if on frames page
                if (router.current === 'frames') {
                    setTimeout(() => {
                        try {
                            const videoId = state.get('selectedVideoId');
                            if (videoId && typeof Frames !== 'undefined' && Frames.loadFrames) {
                                logger.info('App', 'Refreshing frames after training completion', { videoId });
                                Frames.loadFrames(videoId);
                            }
                        } catch (error) {
                            logger.error('App', 'Error refreshing frames after training', error);
                        }
                    }, 1000);
                }
                
                // Refresh dashboard stats
                if (router.current === 'dashboard' && typeof Dashboard !== 'undefined') {
                    if (Dashboard.refreshStats) {
                        setTimeout(() => {
                            Dashboard.refreshStats();
                        }, 1000);
                    }
                }
            }
        });

        // Handle rollback completion
        wsManager.on('rollback_completed', (data) => {
            // Filter by client session ID - only process events for this client
            const currentSessionId = state.get('clientSessionId');
            if (data.client_session_id && data.client_session_id !== currentSessionId) {
                if (CONFIG.ENABLE_WS_LOGGING) {
                    logger.debug('App', 'Ignoring rollback completion for different session', {
                        received: data.client_session_id,
                        current: currentSessionId
                    });
                }
                return; // Ignore events from other sessions
            }

            if (CONFIG.ENABLE_WS_LOGGING) {
                logger.info('App', 'Rollback completed', data);
            }
            
            UI.showToast(`Rollback completed: ${data.frames_reset || 0} frames reset`, 'success');
            
            // Refresh training page if on training page
            if (router.current === 'training') {
                setTimeout(() => {
                    try {
                        if (typeof Training !== 'undefined' && Training.load) {
                            logger.info('App', 'Refreshing training page after rollback');
                            Training.load();
                        }
                    } catch (error) {
                        logger.error('App', 'Error refreshing training page after rollback', error);
                    }
                }, 1000);
            }
            
            // Refresh frames if on frames page
            if (router.current === 'frames') {
                setTimeout(() => {
                    try {
                        const videoId = state.get('selectedVideoId');
                        if (videoId && typeof Frames !== 'undefined' && Frames.loadFrames) {
                            logger.info('App', 'Refreshing frames after rollback', { videoId });
                            Frames.loadFrames(videoId);
                        }
                    } catch (error) {
                        logger.error('App', 'Error refreshing frames after rollback', error);
                    }
                }, 1000);
            }
            
            // Refresh dashboard stats
            if (router.current === 'dashboard' && typeof Dashboard !== 'undefined') {
                if (Dashboard.refreshStats) {
                    setTimeout(() => {
                        Dashboard.refreshStats();
                    }, 1000);
                }
            }
        });
    }

    static async checkHealth() {
        const indicator = document.getElementById('statusIndicator');
        const status = document.getElementById('systemStatus');

        try {
            logger.debug('App', 'Performing health check');
            const health = await API.healthCheck();
            const isHealthy = health.status === 'healthy';

            if (indicator && status) {
                indicator.className = `w-2 h-2 rounded-full ${isHealthy ? 'bg-green-500' : 'bg-yellow-500'} mr-2`;
                status.textContent = isHealthy ? 'All systems operational' : 'Some services degraded';
            }

            logger.info('App', 'Health check completed', { status: health.status, isHealthy });
            UI.showToast(`Health check: ${health.status}`, isHealthy ? 'success' : 'warning');
        } catch (error) {
            logger.error('App', 'Health check failed', error);
            if (indicator && status) {
                indicator.className = 'w-2 h-2 rounded-full bg-red-500 mr-2';
                status.textContent = 'System issues detected';
            }
            UI.showToast('Health check failed', 'error');
        }
    }
}

// Start the application when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    logger.info('App', 'DOM loaded, starting application');
    try {
        App.init();
    } catch (error) {
        logger.error('App', 'Failed to start application', error);
        console.error('Failed to start application:', error);
    }
});

