/**
 * Video Upload Component
 */
class VideoUpload {
    static render() {
        return `
            <form id="uploadForm" class="space-y-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Video File *</label>
                    <div class="mt-1 flex justify-center px-6 pt-5 pb-6 border-2 border-gray-300 border-dashed rounded-lg hover:border-blue-400 transition-colors">
                        <div class="space-y-1 text-center">
                            <i class="fas fa-cloud-upload-alt text-gray-400 text-2xl"></i>
                            <div class="flex text-sm text-gray-600 justify-center">
                                <label for="videoFile" class="relative cursor-pointer bg-white rounded-md font-medium text-blue-600 hover:text-blue-500">
                                    <span>Choose file</span>
                                    <input id="videoFile" type="file" class="sr-only" accept="video/*" required>
                                </label>
                                <p class="pl-1">or drag & drop</p>
                            </div>
                            <p class="text-xs text-gray-500">MP4, AVI, MOV up to 1GB</p>
                        </div>
                    </div>
                    <div id="fileName" class="mt-2 text-sm text-gray-500">No file selected</div>
                    <div id="fileError" class="error-message hidden"></div>
                </div>

                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Asset Name *</label>
                        <input type="text" id="assetName" required class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                        <div id="assetNameError" class="error-message hidden"></div>
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Category *</label>
                        <input type="text" id="category" required class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                        <div id="categoryError" class="error-message hidden"></div>
                    </div>
                </div>

                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Model Number</label>
                        <input type="text" id="modelNumber" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Manufacturer</label>
                        <input type="text" id="manufacturer" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                    </div>
                </div>

                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">AI Attributes</label>
                    <input type="text" id="aiAttributes" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" placeholder="Comma-separated">
                </div>

                <div class="grid grid-cols-3 gap-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Latitude</label>
                        <input type="number" step="any" id="latitude" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" placeholder="-90 to 90">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Longitude</label>
                        <input type="number" step="any" id="longitude" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" placeholder="-180 to 180">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">FPS (1-10) *</label>
                        <input type="number" id="fps" min="1" max="10" value="1" required class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                        <div id="fpsError" class="error-message hidden"></div>
                    </div>
                </div>

                <button type="submit" class="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 flex justify-center items-center transition-colors">
                    <i class="fas fa-upload mr-2"></i>
                    Upload Video
                </button>
            </form>
        `;
    }

    static init() {
        const form = document.getElementById('uploadForm');
        const fileInput = document.getElementById('videoFile');
        const fileName = document.getElementById('fileName');

        if (!form || !fileInput || !fileName) {
            logger.error('VideoUpload', 'Required elements not found');
            return;
        }

        logger.debug('VideoUpload', 'Initializing upload form');

        // File validation
        fileInput.addEventListener('change', (e) => {
            const fileError = document.getElementById('fileError');
            if (fileError) {
                fileError.classList.add('hidden');
            }
            fileInput.classList.remove('input-error');

            if (e.target.files.length > 0) {
                const file = e.target.files[0];
                logger.debug('VideoUpload', 'File selected', { name: file.name, size: file.size, type: file.type });

                // Validate file size
                if (file.size > CONFIG.MAX_FILE_SIZE) {
                    const errorMsg = 'File exceeds 1GB limit';
                    if (fileError) {
                        fileError.textContent = errorMsg;
                        fileError.classList.remove('hidden');
                    }
                    fileInput.classList.add('input-error');
                    fileInput.value = '';
                    fileName.textContent = 'No file selected';
                    logger.warn('VideoUpload', 'File size validation failed', { size: file.size });
                    return;
                }

                // Validate file type
                const validTypes = ['video/mp4', 'video/avi', 'video/quicktime', 'video/x-msvideo'];
                if (!validTypes.includes(file.type)) {
                    const errorMsg = 'Invalid file type. Use MP4, AVI, or MOV';
                    if (fileError) {
                        fileError.textContent = errorMsg;
                        fileError.classList.remove('hidden');
                    }
                    fileInput.classList.add('input-error');
                    fileInput.value = '';
                    fileName.textContent = 'No file selected';
                    logger.warn('VideoUpload', 'File type validation failed', { type: file.type });
                    return;
                }

                fileName.textContent = `${file.name} (${UI.formatBytes(file.size)})`;
                fileName.classList.add('text-green-600');
                logger.debug('VideoUpload', 'File validated successfully');
            }
        });

        // Form validation and submission
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            logger.info('VideoUpload', 'Form submission started');

            // Clear previous errors
            document.querySelectorAll('.error-message').forEach(el => el.classList.add('hidden'));
            document.querySelectorAll('input').forEach(el => el.classList.remove('input-error'));

            let hasError = false;

            // Validate required fields
            const assetName = document.getElementById('assetName');
            const category = document.getElementById('category');
            const fps = document.getElementById('fps');

            if (!assetName || !assetName.value.trim()) {
                const errorEl = document.getElementById('assetNameError');
                if (errorEl) {
                    errorEl.textContent = 'Asset name is required';
                    errorEl.classList.remove('hidden');
                }
                assetName?.classList.add('input-error');
                hasError = true;
            }

            if (!category || !category.value.trim()) {
                const errorEl = document.getElementById('categoryError');
                if (errorEl) {
                    errorEl.textContent = 'Category is required';
                    errorEl.classList.remove('hidden');
                }
                category?.classList.add('input-error');
                hasError = true;
            }

            const fpsValue = fps ? parseInt(fps.value) : null;
            if (!fpsValue || fpsValue < 1 || fpsValue > 10) {
                const errorEl = document.getElementById('fpsError');
                if (errorEl) {
                    errorEl.textContent = 'FPS must be between 1 and 10';
                    errorEl.classList.remove('hidden');
                }
                fps?.classList.add('input-error');
                hasError = true;
            }

            if (!fileInput.files[0]) {
                const errorEl = document.getElementById('fileError');
                if (errorEl) {
                    errorEl.textContent = 'Please select a video file';
                    errorEl.classList.remove('hidden');
                }
                hasError = true;
            }

            if (hasError) {
                UI.showToast('Please fix the errors before submitting', 'error');
                logger.warn('VideoUpload', 'Form validation failed');
                return;
            }

            const formData = new FormData();
            formData.append('video', fileInput.files[0]);
            formData.append('asset_name', assetName.value.trim());
            formData.append('category', category.value.trim());
            formData.append('fps', fpsValue);

            const modelNumber = document.getElementById('modelNumber')?.value.trim();
            const manufacturer = document.getElementById('manufacturer')?.value.trim();
            const aiAttributes = document.getElementById('aiAttributes')?.value.trim();
            const latitude = document.getElementById('latitude')?.value;
            const longitude = document.getElementById('longitude')?.value;

            if (modelNumber) formData.append('model_number', modelNumber);
            if (manufacturer) formData.append('manufacturer', manufacturer);
            if (aiAttributes) formData.append('ai_attributes', aiAttributes);
            if (latitude) formData.append('latitude', latitude);
            if (longitude) formData.append('longitude', longitude);

            UI.showLoading('Uploading video...');

            try {
                logger.info('VideoUpload', 'Uploading video', {
                    filename: fileInput.files[0].name,
                    size: fileInput.files[0].size,
                    assetName: assetName.value.trim()
                });

                const result = await API.uploadVideo(formData);
                UI.showToast(`Video uploaded successfully! ID: ${result.video_id}`, 'success');
                logger.info('VideoUpload', 'Video uploaded successfully', result);

                form.reset();
                fileName.textContent = 'No file selected';
                fileName.classList.remove('text-green-600');

                // Auto-refresh dashboard
                setTimeout(async () => {
                    if (typeof Dashboard !== 'undefined') {
                        if (Dashboard.loadRecentVideos) {
                            await Dashboard.loadRecentVideos();
                        }
                        if (Dashboard.refreshStats) {
                            await Dashboard.refreshStats();
                        }
                    }
                }, 1000);
            } catch (error) {
                logger.error('VideoUpload', 'Upload failed', error);
                UI.handleError(error, 'Video upload');
            } finally {
                UI.hideLoading();
            }
        });
    }
}

