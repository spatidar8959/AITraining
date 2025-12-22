/**
 * Training Component
 * Manages training jobs
 */
class Training {
    static async render() {
        logger.info('Training', 'Rendering training section');
        const content = document.getElementById('content');
        
        if (!content) {
            logger.error('Training', 'Content element not found');
            return;
        }

        try {
            content.innerHTML = `
                <div class="mb-6">
                    <h2 class="text-2xl font-bold text-gray-800">Training Jobs</h2>
                    <p class="text-gray-600 text-sm mt-1">Monitor and manage AI training jobs</p>
                </div>

                <div class="card p-4 mb-6">
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Status</label>
                            <select id="trainingStatusFilter" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                                <option value="">All</option>
                                <option value="pending">Pending</option>
                                <option value="processing">Processing</option>
                                <option value="completed">Completed</option>
                                <option value="failed">Failed</option>
                                <option value="paused">Paused</option>
                                <option value="rolled_back">Rolled Back</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Per Page</label>
                            <select id="trainingPageSize" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                                <option value="10">10</option>
                                <option value="20" selected>20</option>
                                <option value="50">50</option>
                            </select>
                        </div>
                        <div class="flex items-end">
                            <button id="applyTrainingFilters" class="w-full bg-gray-800 text-white py-2 px-4 rounded-md hover:bg-gray-900 text-sm">
                                <i class="fas fa-filter mr-2"></i>Apply Filters
                            </button>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <div id="trainingJobsTable"></div>
                    <div id="trainingPagination" class="p-4 border-t flex justify-between items-center"></div>
                </div>
            `;

            await this.load();
            this.initFilters();
        } catch (error) {
            logger.error('Training', 'Failed to render training section', error);
            UI.handleError(error, 'Training render');
        }
    }

    static async load() {
        const s = state.get();
        UI.showLoading('Loading training jobs...');
        logger.debug('Training', 'Loading training jobs', { page: s.currentTrainingPage || 1, pageSize: s.pageSize });

        try {
            const data = await API.listTrainingJobs(
                s.currentTrainingPage || 1,
                s.pageSize,
                null,
                s.filters.trainingStatus || null
            );

            const table = document.getElementById('trainingJobsTable');
            if (!table) {
                logger.error('Training', 'Training jobs table element not found');
                return;
            }

            if (!data.jobs || data.jobs.length === 0) {
                table.innerHTML = `
                    <div class="text-center py-12 text-gray-500">
                        <i class="fas fa-brain text-4xl mb-4 text-gray-300"></i>
                        <p class="text-lg">No training jobs found</p>
                        <p class="text-sm mt-2">Start training from the Frames section</p>
                    </div>
                `;
            } else {
                table.innerHTML = `
                    <div class="overflow-x-auto">
                        <table class="w-full">
                            <thead>
                                <tr class="text-left text-gray-500 text-sm border-b">
                                    <th class="py-3 px-6">Job ID</th>
                                    <th class="py-3 px-6">Video</th>
                                    <th class="py-3 px-6">Status</th>
                                    <th class="py-3 px-6">Progress</th>
                                    <th class="py-3 px-6">Frames</th>
                                    <th class="py-3 px-6">Started</th>
                                    <th class="py-3 px-6">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.jobs.map(job => {
                                    const isRolledBack = job.status === 'rolled_back';
                                    const canRollback = job.status === 'completed' || job.status === 'failed';
                                    
                                    return `
                                    <tr class="border-b last:border-0 hover:bg-gray-50">
                                        <td class="py-3 px-6 font-medium">#${job.id || 'N/A'}</td>
                                        <td class="py-3 px-6">
                                            <div class="font-medium">${UI.escapeHtml(job.video_name || 'N/A')}</div>
                                            <div class="text-xs text-gray-500">Video ID: ${job.video_id || 'N/A'}</div>
                                        </td>
                                        <td class="py-3 px-6">
                                            <span class="status-badge job-status-${job.status || 'unknown'}">
                                                ${job.status || 'unknown'}
                                                ${isRolledBack ? ' <i class="fas fa-undo text-xs"></i>' : ''}
                                            </span>
                                            ${isRolledBack && job.rolled_back_at ? `
                                                <div class="text-xs text-gray-500 mt-1">
                                                    Rolled back: ${UI.formatDate(job.rolled_back_at)}
                                                </div>
                                            ` : ''}
                                        </td>
                                        <td class="py-3 px-6">
                                            <div class="w-full">
                                                <div class="flex justify-between text-xs mb-1">
                                                    <span>${job.progress_percent || 0}%</span>
                                                    <span>${job.processed_frames || 0}/${job.total_frames || 0}</span>
                                                </div>
                                                <div class="progress-bar">
                                                    <div class="progress-fill" style="width: ${job.progress_percent || 0}%"></div>
                                                </div>
                                            </div>
                                        </td>
                                        <td class="py-3 px-6">
                                            <div class="text-sm">
                                                <div class="text-green-600">✓ ${job.processed_frames || 0}</div>
                                                ${(job.failed_frames || 0) > 0 ? `<div class="text-red-600">✗ ${job.failed_frames}</div>` : ''}
                                            </div>
                                        </td>
                                        <td class="py-3 px-6 text-sm">${UI.formatDate(job.started_at)}</td>
                                        <td class="py-3 px-6">
                                            <div class="flex gap-2">
                                                ${job.status === 'processing' ? `
                                                    <button onclick="Training.pauseJob(${job.id})" class="text-yellow-600 hover:text-yellow-800" title="Pause">
                                                        <i class="fas fa-pause"></i>
                                                    </button>
                                                ` : ''}
                                                ${job.status === 'paused' ? `
                                                    <button onclick="Training.resumeJob(${job.id})" class="text-green-600 hover:text-green-800" title="Resume">
                                                        <i class="fas fa-play"></i>
                                                    </button>
                                                ` : ''}
                                                ${canRollback ? `
                                                    <button onclick="Training.rollbackJob(${job.id})" class="text-orange-600 hover:text-orange-800" title="Rollback">
                                                        <i class="fas fa-undo"></i>
                                                    </button>
                                                ` : ''}
                                                ${isRolledBack ? `
                                                    <span class="text-gray-400" title="Already rolled back">
                                                        <i class="fas fa-check-circle"></i>
                                                    </span>
                                                ` : ''}
                                                ${job.status !== 'processing' ? `
                                                    <button onclick="Training.deleteJob(${job.id})" class="text-red-600 hover:text-red-800" title="Delete">
                                                        <i class="fas fa-trash"></i>
                                                    </button>
                                                ` : ''}
                                                <button onclick="Training.viewDetails(${job.id})" class="text-blue-600 hover:text-blue-800" title="View Details">
                                                    <i class="fas fa-info-circle"></i>
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                    `;
                                }).join('')}
                            </tbody>
                        </table>
                    </div>
                `;
            }

            this.renderPagination(data);
            logger.debug('Training', `Loaded ${data.jobs?.length || 0} training jobs`);

        } catch (error) {
            logger.error('Training', 'Failed to load training jobs', error);
            UI.handleError(error, 'Load training jobs');
        } finally {
            UI.hideLoading();
        }
    }

    static renderPagination(data) {
        try {
            const s = state.get();
            const currentPage = s.currentTrainingPage || 1;
            const totalPages = Math.ceil((data.total || 0) / s.pageSize);
            const pagination = document.getElementById('trainingPagination');
            
            if (!pagination) {
                logger.warn('Training', 'Pagination element not found');
                return;
            }

            pagination.innerHTML = `
                <div class="text-sm text-gray-700">
                    Showing ${((currentPage - 1) * s.pageSize) + 1} to
                    ${Math.min(currentPage * s.pageSize, data.total || 0)} of ${data.total || 0}
                </div>
                <div class="flex gap-2">
                    <button onclick="Training.prevPage()" class="px-3 py-1 border rounded text-sm hover:bg-gray-50" ${currentPage <= 1 ? 'disabled' : ''}>
                        <i class="fas fa-chevron-left"></i> Previous
                    </button>
                    <span class="px-3 py-1 text-sm">Page ${currentPage} of ${totalPages}</span>
                    <button onclick="Training.nextPage()" class="px-3 py-1 border rounded text-sm hover:bg-gray-50" ${currentPage >= totalPages ? 'disabled' : ''}>
                        Next <i class="fas fa-chevron-right"></i>
                    </button>
                </div>
            `;
        } catch (error) {
            logger.error('Training', 'Failed to render pagination', error);
        }
    }

    static initFilters() {
        try {
            const applyBtn = document.getElementById('applyTrainingFilters');
            const pageSizeFilter = document.getElementById('trainingPageSize');

            if (applyBtn) {
                applyBtn.addEventListener('click', () => {
                    const statusFilter = document.getElementById('trainingStatusFilter');
                    state.update({
                        currentTrainingPage: 1,
                        filters: {
                            ...state.get('filters'),
                            trainingStatus: statusFilter?.value || null
                        }
                    });
                    this.load();
                });
            }

            if (pageSizeFilter) {
                pageSizeFilter.addEventListener('change', (e) => {
                    state.update({
                        pageSize: parseInt(e.target.value) || CONFIG.DEFAULT_PAGE_SIZE,
                        currentTrainingPage: 1
                    });
                    this.load();
                });
            }

            logger.debug('Training', 'Filters initialized');
        } catch (error) {
            logger.error('Training', 'Failed to initialize filters', error);
        }
    }

    static async viewDetails(jobId) {
        UI.showLoading('Loading job details...');
        logger.info('Training', `Viewing details for job: ${jobId}`);

        try {
            const job = await API.getTrainingStatus(jobId);
            UI.showModal(`
                <div class="space-y-4">
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="text-sm text-gray-600">Job ID</label>
                            <p class="font-medium">#${job.job_id || jobId}</p>
                        </div>
                        <div>
                            <label class="text-sm text-gray-600">Status</label>
                            <p><span class="status-badge job-status-${job.status || 'unknown'}">${job.status || 'unknown'}</span></p>
                        </div>
                    </div>
                    <div class="grid grid-cols-3 gap-4">
                        <div>
                            <label class="text-sm text-gray-600">Total Frames</label>
                            <p class="font-medium text-lg">${job.total_frames || 0}</p>
                        </div>
                        <div>
                            <label class="text-sm text-gray-600">Processed</label>
                            <p class="font-medium text-lg text-green-600">${job.processed_frames || 0}</p>
                        </div>
                        <div>
                            <label class="text-sm text-gray-600">Failed</label>
                            <p class="font-medium text-lg text-red-600">${job.failed_frames || 0}</p>
                        </div>
                    </div>
                    <div>
                        <label class="text-sm text-gray-600 mb-2 block">Progress</label>
                        <div class="progress-bar" style="height: 8px;">
                            <div class="progress-fill" style="width: ${job.progress_percent || 0}%"></div>
                        </div>
                        <p class="text-sm text-gray-600 mt-1">${job.progress_percent || 0}% complete</p>
                    </div>
                    ${job.started_at ? `<div><label class="text-sm text-gray-600">Started At</label><p class="font-medium">${UI.formatDate(job.started_at)}</p></div>` : ''}
                    ${job.estimated_completion ? `<div><label class="text-sm text-gray-600">Estimated Completion</label><p class="font-medium">${UI.formatDate(job.estimated_completion)}</p></div>` : ''}
                </div>
            `, `Training Job #${jobId}`);
        } catch (error) {
            logger.error('Training', 'Failed to load job details', error);
            UI.handleError(error, 'Load job details');
        } finally {
            UI.hideLoading();
        }
    }

    static async pauseJob(jobId) {
        const confirmed = await UI.confirm('Pause this training job?', 'Pause Training');
        if (!confirmed) return;

        UI.showLoading('Pausing job...');
        try {
            await API.pauseTraining(jobId);
            UI.showToast('Training job paused', 'success');
            await this.load();
        } catch (error) {
            logger.error('Training', 'Failed to pause job', error);
            UI.handleError(error, 'Pause job');
        } finally {
            UI.hideLoading();
        }
    }

    static async resumeJob(jobId) {
        UI.showLoading('Resuming job...');
        try {
            await API.resumeTraining(jobId);
            UI.showToast('Training job resumed', 'success');
            await this.load();
        } catch (error) {
            logger.error('Training', 'Failed to resume job', error);
            UI.handleError(error, 'Resume job');
        } finally {
            UI.hideLoading();
        }
    }

    static async rollbackJob(jobId) {
        const confirmed = await UI.confirm(
            'Rollback this training job? This will remove all embeddings from Qdrant and reset frame status to selected. This action cannot be undone.',
            'Rollback Training'
        );
        if (!confirmed) return;

        UI.showLoading('Rolling back...');
        try {
            await API.rollbackTraining(jobId);
            UI.showToast('Rollback started', 'success');
            
            // Poll for completion with better handling
            let pollCount = 0;
            const maxPolls = 30; // 30 seconds max
            
            const pollInterval = setInterval(async () => {
                pollCount++;
                try {
                    await this.load(); // Refresh job list
                    
                    // Check if job status changed to rolled_back
                    const job = await API.getTrainingStatus(jobId).catch(() => null);
                    if (job && job.status === 'rolled_back') {
                        clearInterval(pollInterval);
                        UI.showToast('Rollback completed successfully', 'success');
                        
                        // Refresh frames if we have a video ID
                        const videoId = state.get('selectedVideoId');
                        if (videoId && typeof Frames !== 'undefined') {
                            setTimeout(() => {
                                Frames.loadFrames(videoId);
                            }, 500);
                        }
                    } else if (pollCount >= maxPolls) {
                        clearInterval(pollInterval);
                        UI.showToast('Rollback may still be processing. Please refresh manually.', 'info');
                    }
                } catch (error) {
                    logger.error('Training', 'Error polling rollback status', error);
                }
            }, 1000);
            
            // Clear interval after max time
            setTimeout(() => {
                clearInterval(pollInterval);
            }, maxPolls * 1000);
            
        } catch (error) {
            logger.error('Training', 'Failed to rollback job', error);
            UI.handleError(error, 'Rollback job');
        } finally {
            UI.hideLoading();
        }
    }

    static async deleteJob(jobId) {
        const confirmed = await UI.confirm('Delete this training job?', 'Delete Job');
        if (!confirmed) return;

        UI.showLoading('Deleting job...');
        try {
            await API.deleteTrainingJob(jobId);
            UI.showToast('Training job deleted', 'success');
            await this.load();
        } catch (error) {
            logger.error('Training', 'Failed to delete job', error);
            UI.handleError(error, 'Delete job');
        } finally {
            UI.hideLoading();
        }
    }

    static prevPage() {
        const page = state.get('currentTrainingPage') || 1;
        if (page > 1) {
            state.set('currentTrainingPage', page - 1);
            this.load();
        }
    }

    static nextPage() {
        state.set('currentTrainingPage', (state.get('currentTrainingPage') || 1) + 1);
        this.load();
    }
}

