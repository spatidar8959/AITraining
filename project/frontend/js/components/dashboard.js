/**
 * Dashboard Component
 */
class Dashboard {
    static async render() {
        UI.showLoading('Loading dashboard...');
        logger.info('Dashboard', 'Rendering dashboard');

        try {
            const [stats, qdrant] = await Promise.all([
                API.getDashboardStats(),
                API.getCollectionInfo()
            ]);

            logger.debug('Dashboard', 'Data loaded', { stats, qdrant });

            const content = document.getElementById('content');
            if (!content) {
                throw new Error('Content element not found');
            }

            content.innerHTML = `
                <!-- Stats Grid -->
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
                    ${this.renderStatCard('Total Videos', stats.videos?.total || 0, 'video', 'blue', [
                        { label: 'Uploaded', value: stats.videos?.uploaded || 0 },
                        { label: 'Extracted', value: stats.videos?.extracted || 0 }
                    ])}
                    ${this.renderStatCard('Total Frames', stats.frames?.total || 0, 'images', 'green', [
                        { label: 'Selected', value: stats.frames?.selected || 0 },
                        { label: 'Trained', value: stats.frames?.trained || 0 }
                    ])}
                    ${this.renderStatCard('Training Jobs', stats.training_jobs?.total || 0, 'brain', 'purple', [
                        { label: 'Processing', value: stats.training_jobs?.processing || 0 },
                        { label: 'Completed', value: stats.training_jobs?.completed || 0 }
                    ])}
                    ${this.renderStatCard('Vector Points', qdrant.points_count || 0, 'database', 'orange', [
                        { label: 'Collection', value: qdrant.collection_name || 'N/A' }
                    ])}
                </div>

                <!-- Upload Video Section (Centered) -->
                <div class="max-w-2xl mx-auto mb-8">
                    <div class="card p-6">
                        <h3 class="text-lg font-semibold text-gray-800 mb-6 text-center">Upload Video</h3>
                        ${VideoUpload.render()}
                    </div>
                </div>

                <!-- Recent Videos -->
                <div class="card p-6">
                    <div class="flex justify-between items-center mb-6">
                        <h3 class="text-lg font-semibold text-gray-800">Recent Videos</h3>
                        <button onclick="router.navigate('videos'); setTimeout(() => { if (typeof Videos !== 'undefined') Videos.load(); }, 100);" class="text-blue-600 hover:text-blue-800 text-sm">
                            View All <i class="fas fa-arrow-right ml-1"></i>
                        </button>
                    </div>
                    <div id="recentVideos"></div>
                </div>
            `;

            await this.loadRecentVideos();
            VideoUpload.init();

            logger.info('Dashboard', 'Dashboard rendered successfully');
        } catch (error) {
            logger.error('Dashboard', 'Failed to render dashboard', error);
            UI.handleError(error, 'Dashboard render');
        } finally {
            UI.hideLoading();
        }
    }

    static renderStatCard(title, value, icon, color, details) {
        const colors = {
            blue: { bg: 'bg-blue-100', text: 'text-blue-600' },
            green: { bg: 'bg-green-100', text: 'text-green-600' },
            purple: { bg: 'bg-purple-100', text: 'text-purple-600' },
            orange: { bg: 'bg-orange-100', text: 'text-orange-600' }
        };

        return `
            <div class="card p-6">
                <div class="flex justify-between items-start">
                    <div>
                        <p class="text-gray-500 text-sm">${UI.escapeHtml(title)}</p>
                        <p class="text-3xl font-bold mt-2">${value}</p>
                    </div>
                    <div class="w-12 h-12 rounded-lg ${colors[color]?.bg || colors.blue.bg} flex items-center justify-center">
                        <i class="fas fa-${icon} ${colors[color]?.text || colors.blue.text} text-xl"></i>
                    </div>
                </div>
                <div class="mt-4 space-y-1">
                    ${details.map(d => `
                        <div class="flex justify-between text-sm">
                            <span class="text-gray-600">${UI.escapeHtml(d.label)}:</span>
                            <span class="font-medium">${d.value}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    static async loadRecentVideos() {
        try {
            logger.debug('Dashboard', 'Loading recent videos');
            const data = await API.listVideos(1, 5);
            const container = document.getElementById('recentVideos');

            if (!container) {
                logger.warn('Dashboard', 'Recent videos container not found');
                return;
            }

            if (!data.videos || data.videos.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8 text-gray-500">
                        <i class="fas fa-video-slash text-3xl mb-2 text-gray-300"></i>
                        <p>No videos yet. Upload your first video above!</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = `
                <div class="overflow-x-auto">
                    <table class="w-full">
                        <thead>
                            <tr class="text-left text-gray-500 text-sm border-b">
                                <th class="pb-3">Video</th>
                                <th class="pb-3">Category</th>
                                <th class="pb-3">Status</th>
                                <th class="pb-3">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.videos.map(v => `
                                <tr class="border-b last:border-0 hover:bg-gray-50">
                                    <td class="py-3">
                                        <div class="font-medium text-sm">${UI.escapeHtml(v.asset_name || 'N/A')}</div>
                                        <div class="text-xs text-gray-500">${UI.escapeHtml(v.filename || 'N/A')}</div>
                                    </td>
                                    <td class="py-3">
                                        <span class="px-2 py-1 text-xs bg-gray-100 rounded">${UI.escapeHtml(v.category || 'N/A')}</span>
                                    </td>
                                    <td class="py-3">
                                        <span class="status-badge status-${v.status || 'unknown'}">${v.status || 'unknown'}</span>
                                    </td>
                                    <td class="py-3">
                                        <button onclick="VideoModal.show(${v.id})" class="text-blue-600 hover:text-blue-800 text-sm">
                                            <i class="fas fa-eye"></i>
                                        </button>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;

            logger.debug('Dashboard', `Loaded ${data.videos.length} recent videos`);
        } catch (error) {
            logger.error('Dashboard', 'Failed to load recent videos', error);
            const container = document.getElementById('recentVideos');
            if (container) {
                container.innerHTML = `
                    <div class="text-center py-8 text-red-500">
                        <i class="fas fa-exclamation-triangle text-3xl mb-2"></i>
                        <p>Failed to load videos</p>
                    </div>
                `;
            }
        }
    }

    // Add a method to refresh stats
    static async refreshStats() {
        try {
            logger.debug('Dashboard', 'Refreshing dashboard stats');
            const [stats, qdrant] = await Promise.all([
                API.getDashboardStats(),
                API.getCollectionInfo()
            ]);

            // Update stats cards
            const statsGrid = document.querySelector('.grid.grid-cols-1.md\\:grid-cols-2.lg\\:grid-cols-4');
            if (statsGrid) {
                statsGrid.innerHTML = `
                    ${this.renderStatCard('Total Videos', stats.videos?.total || 0, 'video', 'blue', [
                        { label: 'Uploaded', value: stats.videos?.uploaded || 0 },
                        { label: 'Extracted', value: stats.videos?.extracted || 0 }
                    ])}
                    ${this.renderStatCard('Total Frames', stats.frames?.total || 0, 'images', 'green', [
                        { label: 'Selected', value: stats.frames?.selected || 0 },
                        { label: 'Trained', value: stats.frames?.trained || 0 }
                    ])}
                    ${this.renderStatCard('Training Jobs', stats.training_jobs?.total || 0, 'brain', 'purple', [
                        { label: 'Processing', value: stats.training_jobs?.processing || 0 },
                        { label: 'Completed', value: stats.training_jobs?.completed || 0 }
                    ])}
                    ${this.renderStatCard('Vector Points', qdrant.points_count || 0, 'database', 'orange', [
                        { label: 'Collection', value: qdrant.collection_name || 'N/A' }
                    ])}
                `;
            }
        } catch (error) {
            logger.error('Dashboard', 'Failed to refresh stats', error);
        }
    }
}

