/**
 * Videos Component
 * Manages video listing and filtering
 */
class Videos {
    static async render() {
        logger.info('Videos', 'Rendering videos section');
        const content = document.getElementById('content');
        
        if (!content) {
            logger.error('Videos', 'Content element not found');
            return;
        }

        // Ensure state is properly initialized
        const s = state.get();
        if (!s.currentVideoPage) {
            state.set('currentVideoPage', 1);
        }
        if (!s.pageSize) {
            state.set('pageSize', CONFIG.DEFAULT_PAGE_SIZE);
        }

        try {
            content.innerHTML = `
                <div class="mb-6">
                    <h2 class="text-2xl font-bold text-gray-800">Video Management</h2>
                    <p class="text-gray-600 text-sm mt-1">Upload, manage, and extract frames from videos</p>
                </div>

                <div class="card p-4 mb-6">
                    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Status</label>
                            <select id="statusFilter" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                                <option value="">All</option>
                                <option value="uploaded">Uploaded</option>
                                <option value="extracting">Extracting</option>
                                <option value="extracted">Extracted</option>
                                <option value="failed">Failed</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Category</label>
                            <select id="categoryFilter" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                                <option value="">All</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Per Page</label>
                            <select id="pageSizeFilter" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                                <option value="10">10</option>
                                <option value="20" selected>20</option>
                                <option value="50">50</option>
                                <option value="100">100</option>
                            </select>
                        </div>
                        <div class="flex items-end">
                            <button id="applyFilters" class="w-full bg-gray-800 text-white py-2 px-4 rounded-md hover:bg-gray-900 text-sm">
                                <i class="fas fa-filter mr-2"></i>Apply Filters
                            </button>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <div id="videosTable"></div>
                    <div id="pagination" class="p-4 border-t flex justify-between items-center"></div>
                </div>
            `;

            await this.load();
            this.initFilters();
        } catch (error) {
            logger.error('Videos', 'Failed to render videos section', error);
            UI.handleError(error, 'Videos render');
        }
    }

    static async load() {
        const s = state.get();
        UI.showLoading('Loading videos...');
        logger.debug('Videos', 'Loading videos', { page: s.currentVideoPage, pageSize: s.pageSize, filters: s.filters });

        try {
            const data = await API.listVideos(
                s.currentVideoPage,
                s.pageSize,
                s.filters.videoStatus,
                s.filters.videoCategory
            );

            logger.debug('Videos', 'Videos loaded', { count: data.videos?.length || 0, total: data.total });

            this.updateCategories(data.videos || []);

            const table = document.getElementById('videosTable');
            if (!table) {
                logger.error('Videos', 'Videos table element not found');
                return;
            }

            if (!data.videos || data.videos.length === 0) {
                table.innerHTML = `
                    <div class="text-center py-12 text-gray-500">
                        <i class="fas fa-video-slash text-4xl mb-4 text-gray-300"></i>
                        <p class="text-lg">No videos found</p>
                        <p class="text-sm mt-2">Try adjusting your filters or upload a new video</p>
                    </div>
                `;
            } else {
                table.innerHTML = `
                    <div class="overflow-x-auto">
                        <table class="w-full">
                            <thead>
                                <tr class="text-left text-gray-500 text-sm border-b">
                                    <th class="py-3 px-6">ID</th>
                                    <th class="py-3 px-6">Asset</th>
                                    <th class="py-3 px-6">Category</th>
                                    <th class="py-3 px-6">Status</th>
                                    <th class="py-3 px-6">Frames</th>
                                    <th class="py-3 px-6">Created</th>
                                    <th class="py-3 px-6">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.videos.map(v => `
                                    <tr class="border-b last:border-0 hover:bg-gray-50">
                                        <td class="py-3 px-6">${v.id || 'N/A'}</td>
                                        <td class="py-3 px-6">
                                            <div class="font-medium">${UI.escapeHtml(v.asset_name || 'N/A')}</div>
                                            <div class="text-xs text-gray-500">${UI.escapeHtml(v.filename || 'N/A')}</div>
                                        </td>
                                        <td class="py-3 px-6">
                                            <span class="px-2 py-1 text-xs bg-gray-100 rounded">${UI.escapeHtml(v.category || 'N/A')}</span>
                                        </td>
                                        <td class="py-3 px-6">
                                            <span class="status-badge status-${v.status || 'unknown'}">${v.status || 'unknown'}</span>
                                        </td>
                                        <td class="py-3 px-6">${v.total_frames || 0}</td>
                                        <td class="py-3 px-6 text-sm">${UI.formatDate(v.created_at)}</td>
                                        <td class="py-3 px-6">
                                            <div class="flex gap-2">
                                                <button onclick="VideoModal.show(${v.id})" class="text-blue-600 hover:text-blue-800" title="View Details">
                                                    <i class="fas fa-eye"></i>
                                                </button>
                                                <button onclick="VideoModal.extract(${v.id}, ${v.status === 'uploaded'})" class="text-green-600 hover:text-green-800 ${v.status !== 'uploaded' ? 'opacity-50 cursor-not-allowed' : ''}" title="Extract Frames">
                                                    <i class="fas fa-layer-group"></i>
                                                </button>
                                                <button onclick="VideoModal.delete(${v.id})" class="text-red-600 hover:text-red-800" title="Delete">
                                                    <i class="fas fa-trash"></i>
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                `;
            }

            this.renderPagination(data);

        } catch (error) {
            logger.error('Videos', 'Failed to load videos', error);
            UI.handleError(error, 'Load videos');
        } finally {
            UI.hideLoading();
        }
    }

    static updateCategories(videos) {
        try {
            const cats = [...new Set(videos.map(v => v.category).filter(Boolean))].sort();
            const select = document.getElementById('categoryFilter');
            if (!select) {
                logger.warn('Videos', 'Category filter element not found');
                return;
            }

            const current = select.value;
            select.innerHTML = '<option value="">All</option>' +
                cats.map(c => `<option value="${UI.escapeHtml(c)}" ${c === current ? 'selected' : ''}>${UI.escapeHtml(c)}</option>`).join('');
            
            logger.debug('Videos', 'Categories updated', { count: cats.length });
        } catch (error) {
            logger.error('Videos', 'Failed to update categories', error);
        }
    }

    static renderPagination(data) {
        try {
            const s = state.get();
            const totalPages = Math.ceil((data.total || 0) / s.pageSize);
            const pagination = document.getElementById('pagination');
            
            if (!pagination) {
                logger.warn('Videos', 'Pagination element not found');
                return;
            }

            pagination.innerHTML = `
                <div class="text-sm text-gray-700">
                    Showing ${((s.currentVideoPage - 1) * s.pageSize) + 1} to
                    ${Math.min(s.currentVideoPage * s.pageSize, data.total || 0)} of ${data.total || 0}
                </div>
                <div class="flex gap-2">
                    <button onclick="Videos.prev()" class="px-3 py-1 border rounded text-sm hover:bg-gray-50" ${s.currentVideoPage <= 1 ? 'disabled' : ''}>
                        <i class="fas fa-chevron-left"></i> Previous
                    </button>
                    <span class="px-3 py-1 text-sm">Page ${s.currentVideoPage} of ${totalPages}</span>
                    <button onclick="Videos.next()" class="px-3 py-1 border rounded text-sm hover:bg-gray-50" ${s.currentVideoPage >= totalPages ? 'disabled' : ''}>
                        Next <i class="fas fa-chevron-right"></i>
                    </button>
                </div>
            `;
        } catch (error) {
            logger.error('Videos', 'Failed to render pagination', error);
        }
    }

    static initFilters() {
        try {
            const applyBtn = document.getElementById('applyFilters');
            const pageSizeFilter = document.getElementById('pageSizeFilter');

            if (applyBtn) {
                applyBtn.addEventListener('click', () => {
                    const statusFilter = document.getElementById('statusFilter');
                    const categoryFilter = document.getElementById('categoryFilter');
                    
                    state.update({
                        currentVideoPage: 1,
                        filters: {
                            ...state.get('filters'),
                            videoStatus: statusFilter?.value || null,
                            videoCategory: categoryFilter?.value || null
                        }
                    });
                    this.load();
                });
            }

            if (pageSizeFilter) {
                pageSizeFilter.addEventListener('change', (e) => {
                    state.update({
                        pageSize: parseInt(e.target.value) || CONFIG.DEFAULT_PAGE_SIZE,
                        currentVideoPage: 1
                    });
                    this.load();
                });
            }

            logger.debug('Videos', 'Filters initialized');
        } catch (error) {
            logger.error('Videos', 'Failed to initialize filters', error);
        }
    }

    static prev() {
        const page = state.get('currentVideoPage');
        if (page > 1) {
            state.set('currentVideoPage', page - 1);
            this.load();
        }
    }

    static next() {
        state.set('currentVideoPage', state.get('currentVideoPage') + 1);
        this.load();
    }
}

