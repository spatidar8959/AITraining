/**
 * Qdrant Component
 * Manages Qdrant vector database
 */
class Qdrant {
    static async render() {
        logger.info('Qdrant', 'Rendering Qdrant section');
        const content = document.getElementById('content');
        
        if (!content) {
            logger.error('Qdrant', 'Content element not found');
            return;
        }

        try {
            content.innerHTML = `
                <div class="space-y-6">
                    <!-- Collection Info Card -->
                    <div class="card">
                        <div class="card-header">
                            <div class="flex items-center">
                                <i class="fas fa-database mr-3 text-purple-600"></i>
                                <h2 class="text-xl font-bold">Qdrant Collection</h2>
                            </div>
                            <button onclick="Qdrant.refreshCollection()" class="btn btn-secondary">
                                <i class="fas fa-sync mr-2"></i>Refresh
                            </button>
                        </div>
                        <div id="collectionInfo" class="p-6">
                            <div class="flex justify-center py-8">
                                <div class="loading-spinner"></div>
                            </div>
                        </div>
                    </div>

                    <!-- Search Section -->
                    <div class="card">
                        <div class="card-header">
                            <h3 class="text-lg font-semibold">Search Vectors</h3>
                        </div>
                        <div class="p-6">
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                                <div>
                                    <label class="form-label">Search Query</label>
                                    <input type="text" id="searchQuery" placeholder="Enter search text..."
                                        class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500">
                                </div>
                                <div>
                                    <label class="form-label">Category Filter</label>
                                    <input type="text" id="searchCategory" placeholder="Optional category..."
                                        class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500">
                                </div>
                            </div>
                            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                                <div>
                                    <label class="form-label">Limit</label>
                                    <input type="number" id="searchLimit" value="10" min="1" max="100"
                                        class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500">
                                </div>
                                <div>
                                    <label class="form-label">Score Threshold</label>
                                    <input type="number" id="searchThreshold" value="0.5" min="0" max="1" step="0.1"
                                        class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500">
                                </div>
                                <div class="flex items-end">
                                    <button onclick="Qdrant.search()" class="btn btn-primary w-full">
                                        <i class="fas fa-search mr-2"></i>Search
                                    </button>
                                </div>
                            </div>
                            <div id="searchResults" class="hidden">
                                <h4 class="font-semibold mb-3">Search Results</h4>
                                <div id="searchResultsList"></div>
                            </div>
                        </div>
                    </div>

                    <!-- Points List -->
                    <div class="card">
                        <div class="card-header">
                            <h3 class="text-lg font-semibold">Vector Points</h3>
                            <div class="flex space-x-2">
                                <button onclick="Qdrant.deleteSelectedPoints()"
                                    class="btn btn-danger" id="deletePointsBtn" disabled>
                                    <i class="fas fa-trash mr-2"></i>Delete Selected
                                </button>
                                <button onclick="Qdrant.loadPoints()" class="btn btn-secondary">
                                    <i class="fas fa-sync mr-2"></i>Refresh
                                </button>
                            </div>
                        </div>
                        <div id="pointsListContainer">
                            <div class="flex justify-center py-8">
                                <div class="loading-spinner"></div>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            await this.loadCollectionInfo();
            await this.loadPoints();
        } catch (error) {
            logger.error('Qdrant', 'Failed to render Qdrant section', error);
            UI.handleError(error, 'Qdrant render');
        }
    }

    static async loadCollectionInfo() {
        try {
            logger.debug('Qdrant', 'Loading collection info');
            const info = await API.getCollectionInfo();
            const container = document.getElementById('collectionInfo');
            
            if (!container) {
                logger.warn('Qdrant', 'Collection info container not found');
                return;
            }

            container.innerHTML = `
                <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div class="text-center">
                        <div class="text-3xl font-bold text-purple-600">${info.points_count || 0}</div>
                        <div class="text-gray-600 mt-1">Total Points</div>
                    </div>
                    <div class="text-center">
                        <div class="text-3xl font-bold text-green-600">${info.vectors_count || 0}</div>
                        <div class="text-gray-600 mt-1">Vectors</div>
                    </div>
                    <div class="text-center">
                        <div class="text-3xl font-bold text-blue-600">${info.status || 'Unknown'}</div>
                        <div class="text-gray-600 mt-1">Status</div>
                    </div>
                </div>
                <div class="mt-4 text-center text-sm text-gray-500">
                    Collection: <span class="font-mono font-semibold">${info.collection_name || 'N/A'}</span>
                </div>
            `;
        } catch (error) {
            logger.error('Qdrant', 'Failed to load collection info', error);
            const container = document.getElementById('collectionInfo');
            if (container) {
                container.innerHTML = `
                    <div class="text-center text-red-600 py-4">
                        <i class="fas fa-exclamation-triangle text-3xl mb-2"></i>
                        <p>Failed to load collection info</p>
                        <p class="text-sm">${UI.escapeHtml(error.message || 'Unknown error')}</p>
                    </div>
                `;
            }
        }
    }

    static async loadPoints() {
        try {
            const limit = 50;
            const offset = ((state.get('currentQdrantPage') || 1) - 1) * limit;
            logger.debug('Qdrant', 'Loading points', { limit, offset });
            
            const data = await API.listPoints(limit, offset);
            const container = document.getElementById('pointsListContainer');
            
            if (!container) {
                logger.warn('Qdrant', 'Points list container not found');
                return;
            }

            if (!data.results || data.results.length === 0) {
                container.innerHTML = `
                    <div class="text-center text-gray-500 py-12">
                        <i class="fas fa-database text-4xl mb-3"></i>
                        <p>No vector points found</p>
                    </div>
                `;
                return;
            }

            let html = `
                <div class="overflow-x-auto">
                    <table class="w-full">
                        <thead class="bg-gray-50">
                            <tr>
                                <th class="px-4 py-3 text-left">
                                    <input type="checkbox" id="selectAllPoints"
                                        onchange="Qdrant.toggleSelectAll(this.checked)"
                                        class="rounded">
                                </th>
                                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Point ID</th>
                                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Category</th>
                                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Asset Name</th>
                                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Frame Number</th>
                                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Score</th>
                                <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Actions</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-200">
            `;

            data.results.forEach(point => {
                const payload = point.payload || {};
                const pointId = point.point_id || point.id;
                const isSelected = state.get('selectedPoints').has(pointId);

                html += `
                    <tr class="hover:bg-gray-50">
                        <td class="px-4 py-3">
                            <input type="checkbox" ${isSelected ? 'checked' : ''}
                                onchange="Qdrant.togglePointSelection('${pointId}', this.checked)"
                                class="rounded point-checkbox">
                        </td>
                        <td class="px-4 py-3">
                            <span class="font-mono text-xs">${UI.escapeHtml(String(pointId).substring(0, 12))}...</span>
                        </td>
                        <td class="px-4 py-3">
                            <span class="px-2 py-1 text-xs rounded-full bg-purple-100 text-purple-800">
                                ${UI.escapeHtml(payload.category || 'N/A')}
                            </span>
                        </td>
                        <td class="px-4 py-3 text-sm">${UI.escapeHtml(payload.asset_name || 'N/A')}</td>
                        <td class="px-4 py-3 text-sm">${payload.frame_number || 'N/A'}</td>
                        <td class="px-4 py-3">
                            ${point.score ?
                                `<span class="text-green-600 font-semibold">${point.score.toFixed(3)}</span>` :
                                '<span class="text-gray-400">-</span>'
                            }
                        </td>
                        <td class="px-4 py-3 text-center">
                            <button onclick="Qdrant.viewPointDetail('${pointId}')"
                                class="text-blue-600 hover:text-blue-800 mr-2" title="View Details">
                                <i class="fas fa-eye"></i>
                            </button>
                            <button onclick="Qdrant.deletePoint('${pointId}')"
                                class="text-red-600 hover:text-red-800" title="Delete">
                                <i class="fas fa-trash"></i>
                            </button>
                        </td>
                    </tr>
                `;
            });

            html += `
                        </tbody>
                    </table>
                </div>
            `;

            const currentPage = state.get('currentQdrantPage') || 1;
            const totalPages = Math.ceil((data.total || 0) / limit);

            if (totalPages > 1) {
                html += `
                    <div class="px-6 py-4 border-t border-gray-200 flex items-center justify-between">
                        <div class="text-sm text-gray-700">
                            Showing ${offset + 1} to ${Math.min(offset + limit, data.total || 0)} of ${data.total || 0} points
                        </div>
                        <div class="flex space-x-2">
                            <button onclick="Qdrant.previousPage()"
                                ${currentPage === 1 ? 'disabled' : ''}
                                class="px-3 py-1 border rounded-lg ${currentPage === 1 ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-50'}">
                                Previous
                            </button>
                            <span class="px-3 py-1">Page ${currentPage} of ${totalPages}</span>
                            <button onclick="Qdrant.nextPage()"
                                ${currentPage === totalPages ? 'disabled' : ''}
                                class="px-3 py-1 border rounded-lg ${currentPage === totalPages ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-50'}">
                                Next
                            </button>
                        </div>
                    </div>
                `;
            }

            container.innerHTML = html;
            this.updateDeleteButton();
            logger.debug('Qdrant', `Loaded ${data.results.length} points`);

        } catch (error) {
            logger.error('Qdrant', 'Failed to load points', error);
            const container = document.getElementById('pointsListContainer');
            if (container) {
                container.innerHTML = `
                    <div class="text-center text-red-600 py-8">
                        <i class="fas fa-exclamation-triangle text-3xl mb-2"></i>
                        <p>Failed to load vector points</p>
                        <p class="text-sm">${UI.escapeHtml(error.message || 'Unknown error')}</p>
                    </div>
                `;
            }
        }
    }

    static async search() {
        const query = document.getElementById('searchQuery')?.value.trim();
        const category = document.getElementById('searchCategory')?.value.trim() || null;
        const limit = parseInt(document.getElementById('searchLimit')?.value) || 10;
        const threshold = parseFloat(document.getElementById('searchThreshold')?.value) || 0.5;

        if (!query) {
            UI.showToast('Please enter a search query', 'warning');
            return;
        }

        try {
            UI.showLoading('Searching vectors...');
            logger.info('Qdrant', 'Searching points', { query, category, limit, threshold });
            
            const data = await API.searchPoints(query, null, limit, threshold, category);
            const resultsContainer = document.getElementById('searchResults');
            const resultsList = document.getElementById('searchResultsList');

            if (!resultsContainer || !resultsList) {
                logger.warn('Qdrant', 'Search results elements not found');
                return;
            }

            if (!data.results || data.results.length === 0) {
                resultsList.innerHTML = `
                    <div class="text-center text-gray-500 py-6">
                        <i class="fas fa-search text-3xl mb-2"></i>
                        <p>No results found</p>
                    </div>
                `;
            } else {
                let html = '<div class="space-y-3">';
                data.results.forEach(result => {
                    const payload = result.payload || {};
                    const pointId = result.point_id || result.id;
                    html += `
                        <div class="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
                            <div class="flex justify-between items-start">
                                <div class="flex-1">
                                    <div class="flex items-center space-x-2 mb-2">
                                        <span class="font-mono text-xs text-gray-500">${UI.escapeHtml(String(pointId).substring(0, 16))}...</span>
                                        <span class="px-2 py-1 text-xs rounded-full bg-purple-100 text-purple-800">
                                            ${UI.escapeHtml(payload.category || 'N/A')}
                                        </span>
                                        ${result.score ?
                                            `<span class="px-2 py-1 text-xs rounded-full bg-green-100 text-green-800 font-semibold">
                                                Score: ${result.score.toFixed(3)}
                                            </span>` : ''
                                        }
                                    </div>
                                    <div class="text-sm">
                                        <div><strong>Asset:</strong> ${UI.escapeHtml(payload.asset_name || 'N/A')}</div>
                                        <div><strong>Frame:</strong> ${payload.frame_number || 'N/A'}</div>
                                        ${payload.manufacturer ? `<div><strong>Manufacturer:</strong> ${UI.escapeHtml(payload.manufacturer)}</div>` : ''}
                                    </div>
                                </div>
                                <button onclick="Qdrant.viewPointDetail('${pointId}')"
                                    class="btn btn-secondary btn-sm">
                                    <i class="fas fa-eye"></i>
                                </button>
                            </div>
                        </div>
                    `;
                });
                html += '</div>';
                resultsList.innerHTML = html;
            }

            resultsContainer.classList.remove('hidden');
            UI.showToast(`Found ${data.total || 0} results`, 'success');
            logger.info('Qdrant', 'Search completed', { results: data.results?.length || 0 });

        } catch (error) {
            logger.error('Qdrant', 'Search failed', error);
            UI.handleError(error, 'Search vectors');
        } finally {
            UI.hideLoading();
        }
    }

    static togglePointSelection(pointId, selected) {
        const selectedPoints = state.get('selectedPoints');
        if (selected) {
            selectedPoints.add(pointId);
        } else {
            selectedPoints.delete(pointId);
        }
        state.set('selectedPoints', selectedPoints);
        this.updateDeleteButton();
    }

    static toggleSelectAll(selected) {
        const checkboxes = document.querySelectorAll('.point-checkbox');
        const selectedPoints = state.get('selectedPoints');

        checkboxes.forEach(cb => {
            cb.checked = selected;
            const pointId = cb.getAttribute('onchange').match(/'([^']+)'/)?.[1];
            if (pointId) {
                if (selected) {
                    selectedPoints.add(pointId);
                } else {
                    selectedPoints.delete(pointId);
                }
            }
        });

        state.set('selectedPoints', selectedPoints);
        this.updateDeleteButton();
    }

    static updateDeleteButton() {
        const btn = document.getElementById('deletePointsBtn');
        const count = state.get('selectedPoints').size;
        if (btn) {
            btn.disabled = count === 0;
            btn.innerHTML = `<i class="fas fa-trash mr-2"></i>Delete Selected ${count > 0 ? `(${count})` : ''}`;
        }
    }

    static async deleteSelectedPoints() {
        const selectedPoints = Array.from(state.get('selectedPoints'));
        if (selectedPoints.length === 0) return;

        const confirmed = await UI.confirm(`Delete ${selectedPoints.length} selected points from Qdrant? This action cannot be undone.`, 'Delete Points');
        if (!confirmed) return;

        try {
            UI.showLoading('Deleting points...');
            logger.info('Qdrant', 'Deleting selected points', { count: selectedPoints.length });
            
            await API.deletePoints(selectedPoints);
            UI.showToast(`Successfully deleted ${selectedPoints.length} points`, 'success');

            state.set('selectedPoints', new Set());
            await this.loadCollectionInfo();
            await this.loadPoints();
        } catch (error) {
            logger.error('Qdrant', 'Failed to delete points', error);
            UI.handleError(error, 'Delete points');
        } finally {
            UI.hideLoading();
        }
    }

    static async deletePoint(pointId) {
        const confirmed = await UI.confirm('Delete this point from Qdrant? This action cannot be undone.', 'Delete Point');
        if (!confirmed) return;

        try {
            UI.showLoading('Deleting point...');
            logger.info('Qdrant', `Deleting point: ${pointId}`);
            
            await API.deletePoints([pointId]);
            UI.showToast('Point deleted successfully', 'success');

            await this.loadCollectionInfo();
            await this.loadPoints();
        } catch (error) {
            logger.error('Qdrant', 'Failed to delete point', error);
            UI.handleError(error, 'Delete point');
        } finally {
            UI.hideLoading();
        }
    }

    static async viewPointDetail(pointId) {
        try {
            UI.showLoading('Loading point details...');
            logger.debug('Qdrant', `Loading point detail: ${pointId}`);
            
            const point = await API.getPointDetail(pointId);
            const payload = point.payload || {};
            const location = payload.location || {};

            // Extract frame_id from point_id if possible (format: video_id_frame_id)
            let frameId = 'N/A';
            let videoId = 'N/A';
            if (pointId && pointId.includes('_')) {
                const parts = pointId.split('_');
                if (parts.length >= 2) {
                    videoId = parts[0];
                    frameId = parts[1];
                }
            }

            const modalContent = `
                <div class="space-y-4">
                    <div>
                        <label class="text-sm font-semibold text-gray-700">Point ID</label>
                        <div class="mt-1 font-mono text-sm bg-gray-100 p-2 rounded break-all">${UI.escapeHtml(String(pointId))}</div>
                    </div>
                    
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="text-sm font-semibold text-gray-700">Video ID</label>
                            <div class="mt-1">${videoId}</div>
                        </div>
                        <div>
                            <label class="text-sm font-semibold text-gray-700">Frame ID</label>
                            <div class="mt-1">${frameId}</div>
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="text-sm font-semibold text-gray-700">Asset Name</label>
                            <div class="mt-1">${UI.escapeHtml(payload.asset_name || 'N/A')}</div>
                        </div>
                        <div>
                            <label class="text-sm font-semibold text-gray-700">Category</label>
                            <div class="mt-1">${UI.escapeHtml(payload.category || 'N/A')}</div>
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="text-sm font-semibold text-gray-700">Model ID</label>
                            <div class="mt-1">${UI.escapeHtml(payload.model_id || payload.model_number || 'N/A')}</div>
                        </div>
                        <div>
                            <label class="text-sm font-semibold text-gray-700">Manufacturer</label>
                            <div class="mt-1">${UI.escapeHtml(payload.manufacturer_name || payload.manufacturer || 'N/A')}</div>
                        </div>
                    </div>

                    <div>
                        <label class="text-sm font-semibold text-gray-700">AI Attributes</label>
                        <div class="mt-1">${UI.escapeHtml(payload.ai_attributes || 'N/A')}</div>
                    </div>

                    <div>
                        <label class="text-sm font-semibold text-gray-700">Image Path (S3)</label>
                        <div class="mt-1 text-sm text-gray-600 break-all">${UI.escapeHtml(payload.image_path || payload.s3_path || 'N/A')}</div>
                    </div>

                    ${location && (location.lat || location.lon) ? `
                        <div>
                            <label class="text-sm font-semibold text-gray-700">Location</label>
                            <div class="mt-1">
                                <div>Latitude: ${location.lat || 'N/A'}</div>
                                <div>Longitude: ${location.lon || 'N/A'}</div>
                            </div>
                        </div>
                    ` : ''}

                    ${payload.image_id ? `
                        <div>
                            <label class="text-sm font-semibold text-gray-700">Image ID</label>
                            <div class="mt-1 font-mono text-sm">${UI.escapeHtml(payload.image_id)}</div>
                        </div>
                    ` : ''}

                    ${payload.frame_number ? `
                        <div>
                            <label class="text-sm font-semibold text-gray-700">Frame Number</label>
                            <div class="mt-1">${payload.frame_number}</div>
                        </div>
                    ` : ''}

                    ${point.score !== null && point.score !== undefined ? `
                        <div>
                            <label class="text-sm font-semibold text-gray-700">Score</label>
                            <div class="mt-1 font-semibold text-green-600">${point.score.toFixed(4)}</div>
                        </div>
                    ` : ''}

                    <div class="flex space-x-2 pt-4 border-t">
                        <button onclick="Qdrant.deletePoint('${pointId}'); document.querySelector('.modal-overlay')?.remove()"
                            class="btn btn-danger flex-1">
                            <i class="fas fa-trash mr-2"></i>Delete Point
                        </button>
                    </div>
                </div>
            `;

            UI.showModal(modalContent, 'Point Details');
        } catch (error) {
            logger.error('Qdrant', 'Failed to load point details', error);
            UI.handleError(error, 'Load point details');
        } finally {
            UI.hideLoading();
        }
    }

    static async refreshCollection() {
        await this.loadCollectionInfo();
        await this.loadPoints();
        UI.showToast('Collection refreshed', 'success');
    }

    static previousPage() {
        const page = state.get('currentQdrantPage') || 1;
        if (page > 1) {
            state.set('currentQdrantPage', page - 1);
            this.loadPoints();
        }
    }

    static nextPage() {
        state.set('currentQdrantPage', (state.get('currentQdrantPage') || 1) + 1);
        this.loadPoints();
    }
}

