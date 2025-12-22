/**
 * Video Modal Component
 */
class VideoModal {
    static currentModal = null; // Store current modal reference

    static async show(videoId) {
        UI.showLoading('Loading video details...');
        logger.info('VideoModal', `Showing video modal for ID: ${videoId}`);

        try {
            const video = await API.getVideoDetail(videoId);
            logger.debug('VideoModal', 'Video details loaded', video);

            const canExtract = video.status === 'uploaded';
            const canViewFrames = video.status === 'extracted' && video.total_frames > 0;

            const modal = UI.showModal(`
                <div class="space-y-6">
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div class="space-y-3">
                            <h4 class="font-medium text-gray-700 border-b pb-2">Video Info</h4>
                            <div class="space-y-2 text-sm">
                                <div class="flex justify-between">
                                    <span class="text-gray-600">ID:</span>
                                    <span class="font-medium">${video.id || 'N/A'}</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-gray-600">Filename:</span>
                                    <span class="font-medium">${UI.escapeHtml(video.filename || 'N/A')}</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-gray-600">Status:</span>
                                    <span class="status-badge status-${video.status || 'unknown'}">${video.status || 'unknown'}</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-gray-600">FPS:</span>
                                    <span class="font-medium">${video.fps || 'N/A'}</span>
                                </div>
                            </div>
                        </div>

                        <div class="space-y-3">
                            <h4 class="font-medium text-gray-700 border-b pb-2">Metadata</h4>
                            <div class="space-y-2 text-sm">
                                <div class="flex justify-between">
                                    <span class="text-gray-600">Asset:</span>
                                    <span class="font-medium">${UI.escapeHtml(video.asset_name || 'N/A')}</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-gray-600">Category:</span>
                                    <span class="font-medium">${UI.escapeHtml(video.category || 'N/A')}</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-gray-600">Model:</span>
                                    <span class="font-medium">${UI.escapeHtml(video.model_number || '-')}</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-gray-600">Manufacturer:</span>
                                    <span class="font-medium">${UI.escapeHtml(video.manufacturer || '-')}</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div>
                        <h4 class="font-medium text-gray-700 mb-4">Frame Stats</h4>
                        <div class="grid grid-cols-4 gap-4">
                            <div class="bg-blue-50 p-4 rounded-lg text-center">
                                <p class="text-sm text-gray-600">Extracted</p>
                                <p class="text-2xl font-bold text-blue-700">${video.frames_extracted || 0}</p>
                            </div>
                            <div class="bg-yellow-50 p-4 rounded-lg text-center">
                                <p class="text-sm text-gray-600">Selected</p>
                                <p class="text-2xl font-bold text-yellow-700">${video.frames_selected || 0}</p>
                            </div>
                            <div class="bg-green-50 p-4 rounded-lg text-center">
                                <p class="text-sm text-gray-600">Trained</p>
                                <p class="text-2xl font-bold text-green-700">${video.frames_trained || 0}</p>
                            </div>
                            <div class="bg-red-50 p-4 rounded-lg text-center">
                                <p class="text-sm text-gray-600">Deleted</p>
                                <p class="text-2xl font-bold text-red-700">${video.frames_deleted || 0}</p>
                            </div>
                        </div>
                    </div>

                    <div class="flex flex-wrap gap-3 pt-4 border-t">
                        <button onclick="VideoModal.editMetadata(${video.id})" class="bg-gray-600 text-white px-4 py-2 rounded-md hover:bg-gray-700">
                            <i class="fas fa-edit mr-2"></i>Edit Metadata
                        </button>
                        <button onclick="VideoModal.viewFrames(${video.id}, ${canViewFrames})" class="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700" ${!canViewFrames ? 'disabled title="Frames not extracted yet"' : ''}>
                            <i class="fas fa-images mr-2"></i>View Frames
                        </button>
                        <button onclick="VideoModal.extract(${video.id}, ${canExtract})" class="bg-green-600 text-white px-4 py-2 rounded-md hover:bg-green-700" ${!canExtract ? 'disabled' : ''}>
                            <i class="fas fa-layer-group mr-2"></i>Extract Frames
                        </button>
                        <button onclick="VideoModal.delete(${video.id})" class="bg-red-600 text-white px-4 py-2 rounded-md hover:bg-red-700">
                            <i class="fas fa-trash mr-2"></i>Delete
                        </button>
                    </div>
                </div>
            `, `Video - ${UI.escapeHtml(video.asset_name || 'Unknown')}`);

            // Store modal reference
            VideoModal.currentModal = modal;
            modal.dataset.videoId = videoId;
            logger.info('VideoModal', 'Video modal displayed successfully');

        } catch (error) {
            logger.error('VideoModal', 'Failed to show video modal', error);
            UI.handleError(error, 'Video modal');
        } finally {
            UI.hideLoading();
        }
    }

    static async editMetadata(videoId) {
        UI.showLoading('Loading...');
        logger.info('VideoModal', `Editing metadata for video: ${videoId}`);

        try {
            const video = await API.getVideoDetail(videoId);

            const editModal = UI.showModal(`
                <form id="editMetadataForm" class="space-y-4">
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Asset Name</label>
                            <input type="text" id="editAssetName" value="${UI.escapeHtml(video.asset_name || '')}" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Category</label>
                            <input type="text" id="editCategory" value="${UI.escapeHtml(video.category || '')}" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Model Number</label>
                            <input type="text" id="editModelNumber" value="${UI.escapeHtml(video.model_number || '')}" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Manufacturer</label>
                            <input type="text" id="editManufacturer" value="${UI.escapeHtml(video.manufacturer || '')}" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                        </div>
                    </div>

                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">AI Attributes</label>
                        <input type="text" id="editAiAttributes" value="${UI.escapeHtml(video.ai_attributes || '')}" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                    </div>

                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Latitude</label>
                            <input type="number" step="any" id="editLatitude" value="${video.latitude || ''}" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Longitude</label>
                            <input type="number" step="any" id="editLongitude" value="${video.longitude || ''}" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                        </div>
                    </div>

                    <div class="flex gap-3 pt-4">
                        <button type="button" class="cancel-edit flex-1 px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50">
                            Cancel
                        </button>
                        <button type="submit" class="flex-1 bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700">
                            Save Changes
                        </button>
                    </div>
                </form>
            `, 'Edit Metadata');

            UI.hideLoading();

            editModal.querySelector('.cancel-edit').addEventListener('click', () => {
                editModal.remove();
            });

            editModal.querySelector('#editMetadataForm').addEventListener('submit', async (e) => {
                e.preventDefault();

                const data = {
                    asset_name: document.getElementById('editAssetName').value,
                    category: document.getElementById('editCategory').value,
                    model_number: document.getElementById('editModelNumber').value,
                    manufacturer: document.getElementById('editManufacturer').value,
                    ai_attributes: document.getElementById('editAiAttributes').value,
                    latitude: document.getElementById('editLatitude').value,
                    longitude: document.getElementById('editLongitude').value
                };

                UI.showLoading('Updating metadata...');

                try {
                    logger.info('VideoModal', 'Updating metadata', { videoId, data });
                    await API.updateVideoMetadata(videoId, data);
                    UI.showToast('Metadata updated successfully', 'success');
                    editModal.remove();

                    document.querySelector('.modal-overlay')?.remove();
                    await VideoModal.show(videoId);
                } catch (error) {
                    logger.error('VideoModal', 'Failed to update metadata', error);
                    UI.handleError(error, 'Metadata update');
                } finally {
                    UI.hideLoading();
                }
            });

        } catch (error) {
            logger.error('VideoModal', 'Failed to load video data for editing', error);
            UI.handleError(error, 'Load video data');
            UI.hideLoading();
        }
    }

    static viewFrames(videoId, canView) {
        if (!canView) {
            UI.showToast('Frames not extracted yet', 'warning');
            return;
        }

        // Ensure videoId is a number, not string
        const numericVideoId = typeof videoId === 'string' ? parseInt(videoId) : videoId;
        
        if (!numericVideoId || isNaN(numericVideoId)) {
            logger.error('VideoModal', 'Invalid video ID', { videoId, numericVideoId });
            UI.showToast('Invalid video ID', 'error');
            return;
        }

        // Force close all modals
        const allModals = document.querySelectorAll('.modal-overlay');
        allModals.forEach(modal => {
            try {
                modal.style.display = 'none';
                modal.remove();
            } catch (e) {
                logger.warn('VideoModal', 'Error removing modal', e);
            }
        });
        
        // Clear any modal references
        VideoModal.currentModal = null;
        
        // Small delay to ensure DOM updates
        setTimeout(() => {
            state.set('selectedVideoId', numericVideoId);
            logger.info('VideoModal', `Navigating to frames for video: ${numericVideoId}`);
            router.navigate('frames', { videoId: numericVideoId });
        }, 100);
    }

    static async extract(videoId, canExtract) {
        if (!canExtract) {
            UI.showToast('Video is not in uploaded status', 'warning');
            return;
        }

        const confirmed = await UI.confirm('Extract frames from this video? This process may take several minutes depending on video length.', 'Extract Frames');
        if (!confirmed) return;

        UI.showLoading('Starting frame extraction...');
        logger.info('VideoModal', `Starting frame extraction for video: ${videoId}`);

        try {
            const result = await API.extractFrames(videoId);
            UI.showToast('Frame extraction started! You will be notified when complete.', 'success');
            logger.info('VideoModal', 'Frame extraction started', result);

            state.state.activeExtractions.set(videoId, result.task_id);
            state.saveState();

            document.querySelector('.modal-overlay')?.remove();

            if (router.current === 'dashboard') {
                await Dashboard.loadRecentVideos();
            } else if (router.current === 'videos') {
                await Videos.load();
            }
        } catch (error) {
            logger.error('VideoModal', 'Failed to start extraction', error);
            UI.handleError(error, 'Frame extraction');
        } finally {
            UI.hideLoading();
        }
    }

    static async delete(videoId) {
        const confirmed = await UI.confirm('Delete this video? All frames, embeddings, and training jobs will be permanently removed. This cannot be undone.', 'Delete Video');
        if (!confirmed) return;

        UI.showLoading('Deleting video...');
        logger.info('VideoModal', `Deleting video: ${videoId}`);

        try {
            const result = await API.deleteVideo(videoId);
            UI.showToast(`Video deleted. Frames: ${result.frames_deleted}, S3 files: ${result.s3_files_deleted}`, 'success');
            logger.info('VideoModal', 'Video deleted successfully', result);

            document.querySelector('.modal-overlay')?.remove();

            if (router.current === 'videos') {
                await Videos.load();
            } else if (router.current === 'dashboard') {
                await Dashboard.render();
            }
        } catch (error) {
            logger.error('VideoModal', 'Failed to delete video', error);
            UI.handleError(error, 'Video deletion');
        } finally {
            UI.hideLoading();
        }
    }
}

