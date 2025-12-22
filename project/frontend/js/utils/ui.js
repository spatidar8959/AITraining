/**
 * UI Utilities
 * Provides common UI functions and components
 */
class UI {
    static showLoading(message = 'Processing...') {
        const overlay = document.getElementById('loadingOverlay');
        const messageEl = document.getElementById('loadingMessage');
        if (overlay && messageEl) {
            messageEl.textContent = message;
            overlay.classList.remove('hidden');
            logger.debug('UI', 'Loading overlay shown', { message });
        }
    }

    static hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.classList.add('hidden');
            logger.debug('UI', 'Loading overlay hidden');
        }
    }

    static showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        if (!container) {
            logger.warn('UI', 'Toast container not found');
            return;
        }

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const icons = {
            success: 'fa-check-circle',
            error: 'fa-exclamation-circle',
            warning: 'fa-exclamation-triangle',
            info: 'fa-info-circle'
        };

        toast.innerHTML = `
            <i class="fas ${icons[type] || icons.info}"></i>
            <span>${this.escapeHtml(message)}</span>
        `;

        container.appendChild(toast);
        logger.info('UI', 'Toast shown', { message, type });

        setTimeout(() => {
            toast.remove();
        }, CONFIG.TOAST_DURATION);
    }

    static showModal(content, title = '') {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal-content">
                ${title ? `
                    <div class="p-6 border-b border-gray-200">
                        <div class="flex justify-between items-center">
                            <h3 class="text-xl font-bold text-gray-800">${this.escapeHtml(title)}</h3>
                            <button class="close-modal text-gray-500 hover:text-gray-700">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    </div>
                ` : ''}
                <div class="p-6">${content}</div>
            </div>
        `;

        document.body.appendChild(modal);

        const closeModal = () => {
            modal.remove();
            document.removeEventListener('keydown', escHandler);
            logger.debug('UI', 'Modal closed');
        };

        modal.querySelector('.close-modal')?.addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        const escHandler = (e) => {
            if (e.key === 'Escape') {
                closeModal();
            }
        };
        document.addEventListener('keydown', escHandler);

        logger.debug('UI', 'Modal shown', { title });
        return modal;
    }

    static async confirm(message, title = 'Confirm') {
        return new Promise((resolve) => {
            const modal = this.showModal(`
                <div class="text-center mb-6">
                    <div class="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center mx-auto mb-4">
                        <i class="fas fa-exclamation-triangle text-red-600 text-xl"></i>
                    </div>
                    <h3 class="text-xl font-bold text-gray-800 mb-2">${this.escapeHtml(title)}</h3>
                    <p class="text-gray-600">${this.escapeHtml(message)}</p>
                </div>
                <div class="flex justify-center gap-3">
                    <button class="cancel-btn px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50">
                        Cancel
                    </button>
                    <button class="confirm-btn bg-red-600 text-white px-4 py-2 rounded-md hover:bg-red-700">
                        Confirm
                    </button>
                </div>
            `);

            modal.querySelector('.cancel-btn').addEventListener('click', () => {
                modal.remove();
                logger.debug('UI', 'Confirm dialog cancelled');
                resolve(false);
            });

            modal.querySelector('.confirm-btn').addEventListener('click', () => {
                modal.remove();
                logger.debug('UI', 'Confirm dialog confirmed');
                resolve(true);
            });
        });
    }

    static formatDate(dateString) {
        if (!dateString) return '-';
        try {
            return new Date(dateString).toLocaleString();
        } catch (error) {
            logger.error('UI', 'Failed to format date', error);
            return dateString;
        }
    }

    static formatBytes(bytes) {
        if (bytes === 0) return '0 Bytes';
        try {
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
        } catch (error) {
            logger.error('UI', 'Failed to format bytes', error);
            return bytes.toString();
        }
    }

    static formatDuration(seconds) {
        if (!seconds) return '-';
        try {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const secs = Math.floor(seconds % 60);

            if (hours > 0) {
                return `${hours}h ${minutes}m`;
            } else if (minutes > 0) {
                return `${minutes}m ${secs}s`;
            } else {
                return `${secs}s`;
            }
        } catch (error) {
            logger.error('UI', 'Failed to format duration', error);
            return seconds.toString();
        }
    }

    static escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    static handleError(error, context = '') {
        const errorMessage = error instanceof APIError 
            ? error.message 
            : error.message || 'An unexpected error occurred';
        
        logger.error('UI', `Error in ${context}`, error);
        this.showToast(errorMessage, 'error');
        
        return errorMessage;
    }
}

