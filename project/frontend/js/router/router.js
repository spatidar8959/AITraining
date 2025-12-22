/**
 * Router
 * Handles client-side routing
 */
class Router {
    constructor() {
        this.routes = new Map();
        this.current = null;
        logger.info('Router', 'Router initialized');
    }

    register(path, handler) {
        this.routes.set(path, handler);
        logger.debug('Router', `Route registered: ${path}`);
    }

    navigate(path, params = {}) {
        const handler = this.routes.get(path);
        if (!handler) {
            logger.warn('Router', `Route not found: ${path}`);
            return;
        }

        logger.info('Router', `Navigating to: ${path}`, { params });
        this.current = path;
        state.set('currentSection', path);

        try {
            window.history.pushState({ path, params }, '', `#${path}`);
            
            // Clear content before rendering to avoid stale data
            const content = document.getElementById('content');
            if (content && path === 'videos') {
                content.innerHTML = ''; // Clear previous content
            }
            
            handler(params);
            this.updateNav(path);
        } catch (error) {
            logger.error('Router', `Error navigating to ${path}`, error);
            UI.handleError(error, `Router navigation to ${path}`);
        }
    }

    updateNav(path) {
        try {
            document.querySelectorAll('.nav-link').forEach(link => {
                if (link.dataset.section === path) {
                    link.classList.add('active');
                } else {
                    link.classList.remove('active');
                }
            });

            const titles = {
                dashboard: 'Dashboard',
                videos: 'Video Management',
                frames: 'Frame Management',
                training: 'Training Jobs',
                qdrant: 'Qdrant Vector DB'
            };
            
            const titleEl = document.getElementById('pageTitle');
            if (titleEl) {
                titleEl.textContent = titles[path] || 'Dashboard';
            }

            const sidebar = document.getElementById('sidebar');
            if (sidebar) {
                sidebar.classList.remove('active');
            }
        } catch (error) {
            logger.error('Router', 'Error updating navigation', error);
        }
    }

    init() {
        window.addEventListener('popstate', (e) => {
            if (e.state && e.state.path) {
                logger.debug('Router', 'Popstate event', { path: e.state.path });
                this.navigate(e.state.path, e.state.params);
            }
        });

        const hash = window.location.hash.slice(1) || 'dashboard';
        logger.info('Router', 'Initializing router', { initialPath: hash });
        this.navigate(hash);
    }
}

// Global router instance
const router = new Router();

