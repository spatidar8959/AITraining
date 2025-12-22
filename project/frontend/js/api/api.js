/**
 * API Service
 * Handles all API requests with comprehensive logging and error handling
 */
class API {
    static async request(endpoint, options = {}) {
        const method = options.method || 'GET';
        const startTime = performance.now();
        
        // Log request
        if (CONFIG.ENABLE_API_LOGGING) {
            logger.info('API', `Request: ${method} ${endpoint}`, {
                endpoint,
                method,
                headers: options.headers,
                body: options.body instanceof FormData ? '[FormData]' : options.body
            });
        }

        try {
            // Prepare headers - don't set Content-Type for FormData
            const headers = { ...options.headers };
            
            // Only set Content-Type if body is not FormData
            // FormData needs browser to set Content-Type with boundary automatically
            if (!(options.body instanceof FormData)) {
                headers['Content-Type'] = 'application/json';
            }
            
            const response = await fetch(`${CONFIG.API_BASE_URL}${endpoint}`, {
                ...options,
                headers: headers
            });

            const duration = performance.now() - startTime;
            const contentType = response.headers.get('content-type');
            let responseData;

            // Parse response based on content type
            if (contentType && contentType.includes('application/json')) {
                responseData = await response.json();
            } else {
                responseData = await response.text();
            }

            if (!response.ok) {
                const error = typeof responseData === 'object' ? responseData : { detail: `HTTP ${response.status}` };
                throw new APIError(
                    error.detail || error.message || `HTTP ${response.status}`,
                    response.status,
                    responseData
                );
            }

            // Log successful response
            if (CONFIG.ENABLE_API_LOGGING) {
                logger.api(method, endpoint, options.body instanceof FormData ? '[FormData]' : options.body, responseData, null);
                logger.info('API', `Response: ${method} ${endpoint} (${duration.toFixed(2)}ms)`, {
                    status: response.status,
                    data: responseData
                });
            }

            // Auto-refresh based on endpoint
            this.handleAutoRefresh(endpoint, method, responseData);

            return responseData;
        } catch (error) {
            const duration = performance.now() - startTime;
            
            // Log error
            if (CONFIG.ENABLE_API_LOGGING) {
                logger.api(method, endpoint, options.body instanceof FormData ? '[FormData]' : options.body, null, error);
                logger.error('API', `Error: ${method} ${endpoint} (${duration.toFixed(2)}ms)`, error);
            }

            // Re-throw with additional context
            if (error instanceof APIError) {
                throw error;
            }
            throw new APIError(
                error.message || 'Network error',
                error.status || 0,
                null,
                error
            );
        }
    }

    static handleAutoRefresh(endpoint, method, responseData) {
        // Only refresh on successful POST/PATCH/DELETE operations
        if (method === 'GET') return;

        try {
            const currentSection = router.current;

            // Video operations
            if (endpoint.includes('/api/video/')) {
                if (method === 'POST' && endpoint.includes('/upload')) {
                    // Video uploaded - refresh dashboard and videos
                    if (currentSection === 'dashboard' && typeof Dashboard !== 'undefined') {
                        setTimeout(() => {
                            Dashboard.loadRecentVideos();
                            Dashboard.refreshStats();
                        }, 1000);
                    }
                    // Always refresh videos section if it exists (even if not current)
                    setTimeout(() => {
                        if (typeof Videos !== 'undefined' && Videos.load) {
                            Videos.load();
                        }
                    }, 1500);
                } else if (method === 'DELETE') {
                    // Video deleted - refresh current page
                    if (currentSection === 'videos' && typeof Videos !== 'undefined') {
                        setTimeout(() => Videos.load(), 500);
                    } else if (currentSection === 'dashboard' && typeof Dashboard !== 'undefined') {
                        setTimeout(() => {
                            Dashboard.loadRecentVideos();
                            Dashboard.refreshStats();
                        }, 500);
                    }
                } else if (method === 'PATCH') {
                    // Video metadata updated - refresh if on videos page
                    if (currentSection === 'videos' && typeof Videos !== 'undefined') {
                        setTimeout(() => Videos.load(), 500);
                    }
                } else if (method === 'POST' && endpoint.includes('/extract')) {
                    // Frame extraction started - will be handled by WebSocket
                }
            }

            // Frame operations
            if (endpoint.includes('/api/frames/')) {
                if (method === 'PATCH' && endpoint.includes('/selection')) {
                    // Frame selection updated - refresh frames if on frames page
                    if (currentSection === 'frames' && typeof Frames !== 'undefined') {
                        const videoId = state.get('selectedVideoId');
                        if (videoId) {
                            setTimeout(() => Frames.loadFrames(videoId), 500);
                        }
                    }
                } else if (method === 'DELETE') {
                    // Frame deleted - refresh frames
                    if (currentSection === 'frames' && typeof Frames !== 'undefined') {
                        const videoId = state.get('selectedVideoId');
                        if (videoId) {
                            setTimeout(() => Frames.loadFrames(videoId), 500);
                        }
                    }
                }
            }

            // Training operations
            if (endpoint.includes('/api/training/')) {
                if (method === 'POST' && endpoint.includes('/rollback')) {
                    // Rollback started - will be handled by WebSocket or polling
                    // But also refresh training page
                    if (currentSection === 'training' && typeof Training !== 'undefined') {
                        setTimeout(() => Training.load(), 2000);
                    }
                    // Refresh frames page if on frames
                    if (currentSection === 'frames' && typeof Frames !== 'undefined') {
                        const videoId = state.get('selectedVideoId');
                        if (videoId) {
                            setTimeout(() => Frames.loadFrames(videoId), 3000);
                        }
                    }
                } else if (method === 'POST' && endpoint.includes('/execute')) {
                    // Training started - refresh training page
                    if (currentSection === 'training' && typeof Training !== 'undefined') {
                        setTimeout(() => Training.load(), 1000);
                    }
                } else if (method === 'POST' && (endpoint.includes('/pause') || endpoint.includes('/resume'))) {
                    // Training paused/resumed - refresh training page
                    if (currentSection === 'training' && typeof Training !== 'undefined') {
                        setTimeout(() => Training.load(), 500);
                    }
                } else if (method === 'POST' && endpoint.includes('/rollback')) {
                    // Training rolled back - refresh training and frames
                    if (currentSection === 'training' && typeof Training !== 'undefined') {
                        setTimeout(() => Training.load(), 1000);
                    }
                    if (currentSection === 'frames' && typeof Frames !== 'undefined') {
                        const videoId = state.get('selectedVideoId');
                        if (videoId) {
                            setTimeout(() => Frames.loadFrames(videoId), 1000);
                        }
                    }
                } else if (method === 'DELETE') {
                    // Training job deleted - refresh training page
                    if (currentSection === 'training' && typeof Training !== 'undefined') {
                        setTimeout(() => Training.load(), 500);
                    }
                }
            }

            // Qdrant operations
            if (endpoint.includes('/api/qdrant/')) {
                if (method === 'DELETE' && endpoint.includes('/points')) {
                    // Points deleted - refresh Qdrant page
                    if (currentSection === 'qdrant' && typeof Qdrant !== 'undefined') {
                        setTimeout(() => {
                            Qdrant.loadCollectionInfo();
                            Qdrant.loadPoints();
                        }, 500);
                    }
                }
            }
        } catch (error) {
            logger.error('API', 'Error in auto-refresh handler', error);
        }
    }

    // Dashboard
    static getDashboardStats() {
        return this.request('/api/dashboard');
    }

    // Videos
    static uploadVideo(formData) {
        return this.request('/api/video/upload', {
            method: 'POST',
            headers: {}, // Let browser set Content-Type for FormData
            body: formData
        });
    }

    static listVideos(page = 1, pageSize = 20, status = null, category = null) {
        let url = `/api/video/list?page=${page}&page_size=${pageSize}`;
        if (status) url += `&status_filter=${status}`;
        if (category) url += `&category_filter=${category}`;
        return this.request(url);
    }

    static getVideoDetail(videoId) {
        return this.request(`/api/video/${videoId}`);
    }

    static updateVideoMetadata(videoId, data) {
        const params = new URLSearchParams();
        Object.keys(data).forEach(key => {
            if (data[key] !== null && data[key] !== undefined && data[key] !== '') {
                params.append(key, data[key]);
            }
        });
        return this.request(`/api/video/${videoId}?${params.toString()}`, {
            method: 'PATCH'
        });
    }

    static deleteVideo(videoId) {
        return this.request(`/api/video/${videoId}`, { method: 'DELETE' });
    }

    static extractFrames(videoId) {
        return this.request(`/api/video/${videoId}/extract`, { method: 'POST' });
    }

    // Frames
    static getVideoFrames(videoId, page = 1, pageSize = 50, status = null) {
        let url = `/api/video/${videoId}/frames?page=${page}&page_size=${pageSize}`;
        if (status) url += `&status_filter=${status}`;
        return this.request(url);
    }

    static updateFrameSelection(frameIds, action) {
        return this.request('/api/frames/selection', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ frame_ids: frameIds, action })
        });
    }

    static deleteFrame(frameId, permanent = false) {
        return this.request(`/api/frames/${frameId}?permanent=${permanent}`, {
            method: 'DELETE'
        });
    }

    static bulkDeleteFrames(frameIds, permanent = false) {
        return this.request('/api/frames/bulk', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ frame_ids: frameIds, permanent })
        });
    }

    // Training
    static listTrainingJobs(page = 1, pageSize = 20, videoId = null, status = null) {
        let url = `/api/training/list?page=${page}&page_size=${pageSize}`;
        if (videoId) url += `&video_id=${videoId}`;
        if (status) url += `&status_filter=${status}`;
        return this.request(url);
    }

    static executeTraining(videoId, frameIds = null) {
        return this.request('/api/training/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ video_id: videoId, frame_ids: frameIds })
        });
    }

    static getTrainingStatus(jobId) {
        return this.request(`/api/training/${jobId}/status`);
    }

    static rollbackTraining(jobId) {
        return this.request(`/api/training/${jobId}/rollback`, { method: 'POST' });
    }

    static resumeTraining(jobId) {
        return this.request(`/api/training/${jobId}/resume`, { method: 'POST' });
    }

    static pauseTraining(jobId) {
        return this.request(`/api/training/${jobId}/pause`, { method: 'POST' });
    }

    static deleteTrainingJob(jobId) {
        return this.request(`/api/training/${jobId}`, { method: 'DELETE' });
    }

    // Qdrant
    static getCollectionInfo() {
        return this.request('/api/qdrant/collection/info');
    }

    static listPoints(limit = 50, offset = null, category = null) {
        let url = `/api/qdrant/points/list?limit=${limit}`;
        if (offset) url += `&offset=${offset}`;
        if (category) url += `&category=${category}`;
        return this.request(url);
    }

    static searchPoints(queryText = null, queryImagePath = null, limit = 10, scoreThreshold = 0.5, filterCategory = null) {
        const body = {
            limit,
            score_threshold: scoreThreshold,
            filter_category: filterCategory
        };
        if (queryText) body.query_text = queryText;
        if (queryImagePath) body.query_image_path = queryImagePath;
        return this.request('/api/qdrant/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
    }

    static deletePoints(pointIds) {
        return this.request('/api/qdrant/points', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ point_ids: pointIds })
        });
    }

    static getPointDetail(pointId) {
        return this.request(`/api/qdrant/point/${pointId}`);
    }

    // System
    static healthCheck() {
        return this.request('/health');
    }
}

/**
 * Custom API Error class
 */
class APIError extends Error {
    constructor(message, status = 0, responseData = null, originalError = null) {
        super(message);
        this.name = 'APIError';
        this.status = status;
        this.responseData = responseData;
        this.originalError = originalError;
    }
}

