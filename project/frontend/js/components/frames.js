/**
 * Frames Component
 * Manages frame display and selection
 */
class Frames {
    static async render(params = {}) {
        logger.info('Frames', 'Rendering frames section', params);
        
        // Get videoId from params or state, ensure it's a number
        let videoId = params.videoId || state.get('selectedVideoId');
        
        // Convert to number if it's a string
        if (typeof videoId === 'string') {
            videoId = parseInt(videoId);
        }
        
        // Validate videoId
        if (!videoId || isNaN(videoId)) {
            logger.error('Frames', 'Invalid video ID', { params, videoId, stateVideoId: state.get('selectedVideoId') });
            const content = document.getElementById('content');
            if (content) {
                content.innerHTML = `
                    <div class="card p-12 text-center">
                        <i class="fas fa-images text-6xl text-gray-300 mb-4"></i>
                        <h3 class="text-2xl font-bold text-gray-800 mb-2">Frame Management</h3>
                        <p class="text-gray-600 mb-4">Invalid video ID. Please select a video first.</p>
                        <button onclick="router.navigate('videos')" class="bg-blue-600 text-white px-6 py-2 rounded-md hover:bg-blue-700">
                            Go to Videos
                        </button>
                    </div>
                `;
            }
            return;
        }

        state.set('selectedVideoId', videoId);
        const content = document.getElementById('content');
        
        if (!content) {
            logger.error('Frames', 'Content element not found');
            return;
        }

        try {
            content.innerHTML = `
                <div class="mb-6">
                    <button onclick="router.navigate('videos')" class="text-blue-600 hover:text-blue-800 text-sm mb-2">
                        <i class="fas fa-arrow-left mr-1"></i> Back to Videos
                    </button>
                    <h2 class="text-2xl font-bold text-gray-800">Frame Management</h2>
                    <p class="text-gray-600 text-sm mt-1" id="videoInfo">Loading video info...</p>
                </div>

                <div class="card p-4 mb-6">
                    <div class="flex justify-between items-center flex-wrap gap-4">
                        <div class="flex gap-2">
                            <select id="frameStatusFilter" class="px-3 py-2 border border-gray-300 rounded-md text-sm">
                                <option value="">All Status</option>
                                <option value="extracted">Extracted</option>
                                <option value="selected">Selected</option>
                                <option value="trained">Trained</option>
                            </select>
                            <button id="applyFrameFilters" class="bg-gray-800 text-white px-4 py-2 rounded-md hover:bg-gray-900 text-sm">
                                Apply
                            </button>
                        </div>
                        <div class="flex gap-2">
                            <button id="selectAllFrames" class="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 text-sm">
                                <i class="fas fa-check-square mr-1"></i> Select All
                            </button>
                            <button id="deselectAllFrames" class="bg-gray-600 text-white px-4 py-2 rounded-md hover:bg-gray-700 text-sm">
                                <i class="fas fa-square mr-1"></i> Deselect All
                            </button>
                            <button id="deleteSelectedFrames" class="bg-red-600 text-white px-4 py-2 rounded-md hover:bg-red-700 text-sm">
                                <i class="fas fa-trash mr-1"></i> Delete Selected
                            </button>
                            <button id="trainSelectedFrames" class="bg-green-600 text-white px-4 py-2 rounded-md hover:bg-green-700 text-sm">
                                <i class="fas fa-brain mr-1"></i> Train Selected
                            </button>
                        </div>
                    </div>
                    <div id="selectionInfo" class="mt-3 text-sm text-gray-600"></div>
                </div>

                <div class="card p-6">
                    <div id="framesGrid"></div>
                    <div id="framesPagination" class="mt-6 flex justify-between items-center"></div>
                </div>
            `;

            await this.loadVideoInfo(videoId);
            await this.loadFrames(videoId);
            this.initFrameHandlers(videoId);
        } catch (error) {
            logger.error('Frames', 'Failed to render frames section', error);
            UI.handleError(error, 'Frames render');
        }
    }

    static async loadVideoInfo(videoId) {
        try {
            const video = await API.getVideoDetail(videoId);
            const infoEl = document.getElementById('videoInfo');
            if (infoEl) {
                infoEl.textContent = `Video: ${video.asset_name || 'Unknown'} (${video.total_frames || 0} frames extracted)`;
            }
        } catch (error) {
            logger.error('Frames', 'Failed to load video info', error);
        }
    }

    static async loadFrames(videoId) {
        const s = state.get();
        UI.showLoading('Loading frames...');
        logger.debug('Frames', 'Loading frames', { videoId, page: s.currentFramePage, pageSize: s.framePageSize });

        try {
            const data = await API.getVideoFrames(
                videoId,
                s.currentFramePage,
                s.framePageSize,
                s.filters.frameStatus
            );

            const grid = document.getElementById('framesGrid');
            if (!grid) {
                logger.error('Frames', 'Frames grid element not found');
                return;
            }

            // Get all frame IDs for current video to filter selectedFrames
            const currentVideoFrameIds = new Set(data.frames.map(f => f.id));
            
            // Remove frames from selectedFrames that don't belong to current video
            const framesToRemove = [];
            s.selectedFrames.forEach(frameId => {
                if (!currentVideoFrameIds.has(frameId)) {
                    framesToRemove.push(frameId);
                }
            });
            framesToRemove.forEach(frameId => {
                s.selectedFrames.delete(frameId);
            });
            
            if (framesToRemove.length > 0) {
                state.saveState();
                logger.debug('Frames', `Removed ${framesToRemove.length} frames from other videos from selection`);
            }

            // Sync selectedFrames Set - remove trained/deleted frames
            const trainedOrDeletedFrames = data.frames
                .filter(frame => {
                    const frameStatus = String(frame.status || 'unknown').toLowerCase();
                    return frameStatus === 'trained' || frameStatus === 'deleted';
                })
                .map(frame => frame.id);
            
            trainedOrDeletedFrames.forEach(frameId => {
                s.selectedFrames.delete(frameId);
            });
            
            if (trainedOrDeletedFrames.length > 0) {
                state.saveState();
                logger.debug('Frames', `Removed ${trainedOrDeletedFrames.length} trained/deleted frames from selection`);
            }

            if (!data.frames || data.frames.length === 0) {
                grid.innerHTML = `
                    <div class="text-center py-12 text-gray-500">
                        <i class="fas fa-images text-4xl mb-4 text-gray-300"></i>
                        <p class="text-lg">No frames found</p>
                    </div>
                `;
            } else {
                grid.innerHTML = `
                    <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                        ${data.frames.map(frame => {
                            // Ensure status is a string
                            const frameStatus = String(frame.status || 'unknown').toLowerCase();
                            
                            // Only show as checked if:
                            // 1. Frame is in selectedFrames Set AND
                            // 2. Frame status is NOT 'trained' or 'deleted'
                            const isSelectable = frameStatus !== 'trained' && frameStatus !== 'deleted';
                            const isSelected = isSelectable && s.selectedFrames.has(frame.id);
                            const isDisabled = !isSelectable;
                            
                            return `
                            <div class="frame-card ${isSelected ? 'selected' : ''}" data-frame-id="${frame.id}">
                                <input 
                                    type="checkbox" 
                                    class="frame-checkbox" 
                                    data-frame-id="${frame.id}" 
                                    ${isSelected ? 'checked' : ''}
                                    ${isDisabled ? 'disabled' : ''}
                                    ${isDisabled ? 'title="This frame is already trained or deleted"' : ''}
                                >
                                <img src="${UI.escapeHtml(frame.thumbnail_url || '')}" alt="Frame ${frame.frame_number}" class="frame-thumbnail" onclick="Frames.viewFrame('${UI.escapeHtml(frame.thumbnail_url || '')}', ${frame.frame_number})">
                                <div class="p-2">
                                    <div class="flex justify-between items-center">
                                        <div class="text-xs text-gray-600">Frame #${frame.frame_number || 'N/A'}</div>
                                        <button onclick="Frames.deleteFrame(${frame.id})" class="text-red-600 hover:text-red-800 text-xs" title="Delete">
                                            <i class="fas fa-trash"></i>
                                        </button>
                                    </div>
                                    <span class="status-badge frame-status-${frameStatus} text-xs mt-1">${frameStatus}</span>
                                </div>
                            </div>
                            `;
                        }).join('')}
                    </div>
                `;

                grid.querySelectorAll('.frame-checkbox').forEach(checkbox => {
                    checkbox.addEventListener('change', async (e) => {
                        const frameId = parseInt(e.target.dataset.frameId);
                        const card = grid.querySelector(`.frame-card[data-frame-id="${frameId}"]`);
                        const isChecked = e.target.checked;

                        // Prevent selection of trained/deleted frames
                        const frame = data.frames.find(f => f.id === frameId);
                        if (frame) {
                            const frameStatus = String(frame.status || 'unknown').toLowerCase();
                            if (frameStatus === 'trained' || frameStatus === 'deleted') {
                                e.target.checked = false;
                                UI.showToast('Cannot select trained or deleted frames', 'warning');
                                return;
                            }
                        }

                        try {
                            // Update in database via API
                            const action = isChecked ? 'select' : 'deselect';
                            await API.updateFrameSelection([frameId], action);
                            
                            // Update local state
                            if (isChecked) {
                                s.selectedFrames.add(frameId);
                                if (card) card.classList.add('selected');
                            } else {
                                s.selectedFrames.delete(frameId);
                                if (card) card.classList.remove('selected');
                            }

                            state.saveState();
                            this.updateSelectionInfo();
                            logger.debug('Frames', `Frame ${frameId} ${action}ed`);
                        } catch (error) {
                            // Revert checkbox state on error
                            e.target.checked = !isChecked;
                            logger.error('Frames', `Failed to ${isChecked ? 'select' : 'deselect'} frame`, error);
                            UI.handleError(error, `${isChecked ? 'Select' : 'Deselect'} frame`);
                        }
                    });
                });
            }

            this.renderFramesPagination(data);
            this.updateSelectionInfo();
            logger.debug('Frames', `Loaded ${data.frames?.length || 0} frames`);

        } catch (error) {
            logger.error('Frames', 'Failed to load frames', error);
            UI.handleError(error, 'Load frames');
        } finally {
            UI.hideLoading();
        }
    }

    static viewFrame(url, frameNumber) {
        UI.showModal(`
            <div class="text-center">
                <img src="${UI.escapeHtml(url)}" alt="Frame ${frameNumber}" class="max-w-full h-auto rounded-lg">
                <p class="mt-4 text-gray-600">Frame #${frameNumber}</p>
            </div>
        `, `Frame #${frameNumber}`);
    }

    static updateSelectionInfo() {
        const count = state.get('selectedFrames').size;
        const info = document.getElementById('selectionInfo');
        if (info) {
            info.textContent = `${count} frame(s) selected`;
        }
    }

    static renderFramesPagination(data) {
        try {
            const s = state.get();
            const totalPages = Math.ceil((data.total || 0) / s.framePageSize);
            const pagination = document.getElementById('framesPagination');
            
            if (!pagination) {
                logger.warn('Frames', 'Pagination element not found');
                return;
            }

            pagination.innerHTML = `
                <div class="text-sm text-gray-700">
                    Showing ${((s.currentFramePage - 1) * s.framePageSize) + 1} to
                    ${Math.min(s.currentFramePage * s.framePageSize, data.total || 0)} of ${data.total || 0} frames
                </div>
                <div class="flex gap-2">
                    <button onclick="Frames.prevPage()" class="px-3 py-1 border rounded text-sm hover:bg-gray-50" ${s.currentFramePage <= 1 ? 'disabled' : ''}>
                        <i class="fas fa-chevron-left"></i> Previous
                    </button>
                    <span class="px-3 py-1 text-sm">Page ${s.currentFramePage} of ${totalPages}</span>
                    <button onclick="Frames.nextPage()" class="px-3 py-1 border rounded text-sm hover:bg-gray-50" ${s.currentFramePage >= totalPages ? 'disabled' : ''}>
                        Next <i class="fas fa-chevron-right"></i>
                    </button>
                </div>
            `;
        } catch (error) {
            logger.error('Frames', 'Failed to render pagination', error);
        }
    }

    static initFrameHandlers(videoId) {
        try {
            const applyBtn = document.getElementById('applyFrameFilters');
            const selectAllBtn = document.getElementById('selectAllFrames');
            const deselectAllBtn = document.getElementById('deselectAllFrames');
            const trainBtn = document.getElementById('trainSelectedFrames');
            const deleteSelectedBtn = document.getElementById('deleteSelectedFrames');

            if (applyBtn) {
                applyBtn.addEventListener('click', () => {
                    const filter = document.getElementById('frameStatusFilter');
                    state.update({
                        currentFramePage: 1,
                        filters: {
                            ...state.get('filters'),
                            frameStatus: filter?.value || null
                        }
                    });
                    this.loadFrames(videoId);
                });
            }

            if (selectAllBtn) {
                selectAllBtn.addEventListener('click', async () => {
                    // Only select frames that are not trained or deleted
                    const checkboxes = document.querySelectorAll('.frame-checkbox:not(:checked):not(:disabled)');
                    const frameIds = Array.from(checkboxes).map(cb => parseInt(cb.dataset.frameId));

                    if (frameIds.length === 0) {
                        UI.showToast('All selectable frames are already selected', 'info');
                        return;
                    }

                    UI.showLoading('Selecting frames...');
                    try {
                        // Update in database
                        await API.updateFrameSelection(frameIds, 'select');
                        
                        // Update local state and UI
                        frameIds.forEach(id => {
                            state.state.selectedFrames.add(id);
                            const checkbox = document.querySelector(`.frame-checkbox[data-frame-id="${id}"]`);
                            const card = document.querySelector(`.frame-card[data-frame-id="${id}"]`);
                            if (checkbox) checkbox.checked = true;
                            if (card) card.classList.add('selected');
                        });
                        
                        state.saveState();
                        this.updateSelectionInfo();
                        UI.showToast(`${frameIds.length} frames selected`, 'success');
                    } catch (error) {
                        logger.error('Frames', 'Failed to select frames', error);
                        UI.handleError(error, 'Select frames');
                    } finally {
                        UI.hideLoading();
                    }
                });
            }

            if (deselectAllBtn) {
                deselectAllBtn.addEventListener('click', async () => {
                    const checkboxes = document.querySelectorAll('.frame-checkbox:checked');
                    const frameIds = Array.from(checkboxes).map(cb => parseInt(cb.dataset.frameId));

                    if (frameIds.length === 0) {
                        UI.showToast('No frames to deselect', 'info');
                        return;
                    }

                    UI.showLoading('Deselecting frames...');
                    try {
                        // Update in database
                        await API.updateFrameSelection(frameIds, 'deselect');
                        
                        // Update local state and UI
                        frameIds.forEach(id => {
                            state.state.selectedFrames.delete(id);
                            const checkbox = document.querySelector(`.frame-checkbox[data-frame-id="${id}"]`);
                            const card = document.querySelector(`.frame-card[data-frame-id="${id}"]`);
                            if (checkbox) checkbox.checked = false;
                            if (card) card.classList.remove('selected');
                        });
                        
                        state.saveState();
                        this.updateSelectionInfo();
                        UI.showToast(`${frameIds.length} frames deselected`, 'success');
                    } catch (error) {
                        logger.error('Frames', 'Failed to deselect frames', error);
                        UI.handleError(error, 'Deselect frames');
                    } finally {
                        UI.hideLoading();
                    }
                });
            }

            if (trainBtn) {
                trainBtn.addEventListener('click', async () => {
                    let selected = Array.from(state.get('selectedFrames'));

                    if (selected.length === 0) {
                        UI.showToast('Please select frames first', 'warning');
                        return;
                    }

                    // First, filter to only include frames from current video
                    // Get all frames for current video to verify frame IDs belong to this video
                    try {
                        const allFramesData = await API.getVideoFrames(
                            videoId,
                            1,
                            100, // Get first 100 to check frame IDs
                            null
                        );
                        
                        const currentVideoFrameIds = new Set(allFramesData.frames.map(f => f.id));
                        const framesFromOtherVideos = selected.filter(id => !currentVideoFrameIds.has(id));
                        
                        if (framesFromOtherVideos.length > 0) {
                            logger.warn('Frames', `Removing ${framesFromOtherVideos.length} frames from other videos`, framesFromOtherVideos);
                            // Remove frames from other videos from selection
                            framesFromOtherVideos.forEach(id => {
                                state.get('selectedFrames').delete(id);
                            });
                            state.saveState();
                            
                            // Update selected to only include current video frames
                            selected = selected.filter(id => currentVideoFrameIds.has(id));
                            
                            if (selected.length === 0) {
                                UI.showToast('No frames selected for this video. Please select frames from current video.', 'warning');
                                this.updateSelectionInfo();
                                return;
                            }
                            
                            UI.showToast(`Removed ${framesFromOtherVideos.length} frame(s) from other videos`, 'info');
                        }
                    } catch (error) {
                        logger.warn('Frames', 'Could not verify frame video ownership, proceeding with all selected', error);
                    }

                    // Filter out trained/deleted frames from selection
                    const selectableFrames = [];
                    const invalidFrames = [];
                    
                    // Check frame statuses before training (only if reasonable number)
                    if (selected.length <= 50) {
                        try {
                            // Get frames in batches of 100 (API limit)
                            const framesData = await API.getVideoFrames(
                                videoId,
                                1,
                                100, // Use API limit
                                null
                            );
                            
                            selected.forEach(frameId => {
                                const frame = framesData.frames?.find(f => f.id === frameId);
                                if (frame) {
                                    const status = String(frame.status || '').toLowerCase();
                                    if (status === 'selected' || status === 'extracted') {
                                        selectableFrames.push(frameId);
                                    } else {
                                        invalidFrames.push({ id: frameId, status: status });
                                    }
                                } else {
                                    // Frame not found in current video - skip it
                                    logger.warn('Frames', `Frame ${frameId} not found in current video, skipping`);
                                }
                            });
                            
                            if (invalidFrames.length > 0) {
                                const invalidIds = invalidFrames.map(f => f.id);
                                UI.showToast(
                                    `Cannot train ${invalidIds.length} frame(s). They are ${invalidFrames.map(f => f.status).join(', ')}. Please select only extracted/selected frames.`,
                                    'warning'
                                );
                                
                                // Remove invalid frames from selection
                                invalidIds.forEach(id => {
                                    state.get('selectedFrames').delete(id);
                                });
                                state.saveState();
                                this.updateSelectionInfo();
                                
                                if (selectableFrames.length === 0) {
                                    return;
                                }
                            }
                        } catch (error) {
                            logger.warn('Frames', 'Could not verify frame statuses, proceeding with training', error);
                            // Proceed with all selected frames if check fails
                            selectableFrames.push(...selected);
                        }
                    } else {
                        // Too many frames, skip status check and let backend validate
                        selectableFrames.push(...selected);
                        logger.info('Frames', 'Skipping status check for large selection, backend will validate');
                    }

                    // Deduplicate frame IDs before sending
                    const uniqueFrames = [...new Set(selectableFrames)];

                    if (uniqueFrames.length === 0) {
                        UI.showToast('No valid frames to train', 'warning');
                        return;
                    }

                    const confirmed = await UI.confirm(
                        `Train ${uniqueFrames.length} selected frame(s)? This will generate embeddings and store them in Qdrant.`,
                        'Start Training'
                    );

                    if (!confirmed) return;

                    UI.showLoading('Starting training...');
                    try {
                        const result = await API.executeTraining(videoId, uniqueFrames);
                        UI.showToast(`Training started! Job ID: ${result.job_id}`, 'success');
                        logger.info('Frames', 'Training started', result);

                        // Clear selection after training starts
                        state.set('selectedFrames', new Set());
                        state.saveState();
                        this.updateSelectionInfo();

                        setTimeout(() => {
                            router.navigate('training');
                        }, 1500);
                    } catch (error) {
                        logger.error('Frames', 'Failed to start training', error);
                        
                        // Show detailed error message
                        let errorMsg = error.message || 'Failed to start training';
                        if (errorMsg.includes('Invalid or non-selected')) {
                            errorMsg += '. Please refresh the page and select frames again.';
                        }
                        if (errorMsg.includes('Frames from different video')) {
                            errorMsg += ' Please select only frames from the current video.';
                        }
                        UI.handleError(error, errorMsg);
                    } finally {
                        UI.hideLoading();
                    }
                });
            }

            if (deleteSelectedBtn) {
                deleteSelectedBtn.addEventListener('click', async () => {
                    await this.deleteSelectedFrames();
                });
            }

            logger.debug('Frames', 'Frame handlers initialized');
        } catch (error) {
            logger.error('Frames', 'Failed to initialize frame handlers', error);
        }
    }

    static prevPage() {
        const page = state.get('currentFramePage');
        if (page > 1) {
            state.set('currentFramePage', page - 1);
            this.loadFrames(state.get('selectedVideoId'));
        }
    }

    static nextPage() {
        state.set('currentFramePage', state.get('currentFramePage') + 1);
        this.loadFrames(state.get('selectedVideoId'));
    }

    static async deleteFrame(frameId) {
        const confirmed = await UI.confirm('Delete this frame? This action cannot be undone.', 'Delete Frame');
        if (!confirmed) return;

        UI.showLoading('Deleting frame...');
        logger.info('Frames', `Deleting frame: ${frameId}`);

        try {
            await API.deleteFrame(frameId, false);
            UI.showToast('Frame deleted successfully', 'success');
            
            // Remove from selected frames if selected
            const selectedFrames = state.get('selectedFrames');
            selectedFrames.delete(frameId);
            state.saveState();
            
            await this.loadFrames(state.get('selectedVideoId'));
        } catch (error) {
            logger.error('Frames', 'Failed to delete frame', error);
            UI.handleError(error, 'Delete frame');
        } finally {
            UI.hideLoading();
        }
    }

    static async deleteSelectedFrames() {
        const selected = Array.from(state.get('selectedFrames'));
        if (selected.length === 0) {
            UI.showToast('Please select frames first', 'warning');
            return;
        }

        const confirmed = await UI.confirm(
            `Delete ${selected.length} selected frame(s)? This action cannot be undone.`,
            'Delete Frames'
        );
        if (!confirmed) return;

        UI.showLoading('Deleting frames...');
        logger.info('Frames', `Deleting ${selected.length} frames`);

        try {
            await API.bulkDeleteFrames(selected, false);
            UI.showToast(`Successfully deleted ${selected.length} frames`, 'success');
            
            // Clear selection
            state.set('selectedFrames', new Set());
            await this.loadFrames(state.get('selectedVideoId'));
        } catch (error) {
            logger.error('Frames', 'Failed to delete frames', error);
            UI.handleError(error, 'Delete frames');
        } finally {
            UI.hideLoading();
        }
    }
}

