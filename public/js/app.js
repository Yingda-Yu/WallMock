(function() {
    let templates = [];
    let canvasPresets = {};
    let images = [];
    let currentTemplate = 'phone_hero';
    let currentCanvas = '1:1';
    let previewTimer = null;

    function $(sel) { return document.querySelector(sel); }
    function $$(sel) { return document.querySelectorAll(sel); }
    function on(sel, evt, cb) { const el = $(sel); if (el) el.addEventListener(evt, cb); }

    function showToast(msg, type) {
        type = type || '';
        const t = $('#toast');
        t.textContent = msg;
        t.className = 'toast show ' + type;
        clearTimeout(t._timer);
        t._timer = setTimeout(function() { t.className = 'toast'; }, 2500);
    }

    async function api(url, method, data) {
        method = method || 'GET';
        const opts = { method: method, headers: {} };
        if (data) {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(data);
        }
        const res = await fetch(url, opts);
        return await res.json();
    }

    async function loadCanvasPresets() {
        try {
            const data = await api('/api/canvas-presets');
            canvasPresets = data.presets || {};
            const sel = $('#canvasPreset');
            sel.innerHTML = '';
            for (const key in canvasPresets) {
                const p = canvasPresets[key];
                const opt = document.createElement('option');
                opt.value = key;
                opt.textContent = key + ' ' + p.name;
                sel.appendChild(opt);
            }
            sel.value = currentCanvas;
        } catch (e) {
            console.error('Canvas presets load error:', e);
        }
    }

    async function loadTemplates() {
        const data = await api('/api/templates');
        templates = data.templates || [];

        const sel = $('#templateSelect');
        const groups = { hero: [], collection: [], info: [] };
        templates.forEach(function(t) {
            const cat = t.category || 'hero';
            if (!groups[cat]) groups[cat] = [];
            groups[cat].push(t);
        });

        sel.innerHTML = '';
        const groupLabels = {
            hero: 'HERO',
            collection: 'COLLECTION',
            info: 'INFO'
        };

        for (const cat of ['hero', 'collection', 'info']) {
            if (!groups[cat] || !groups[cat].length) continue;
            const og = document.createElement('optgroup');
            og.label = groupLabels[cat] || cat.toUpperCase();
            groups[cat].forEach(function(t) {
                const opt = document.createElement('option');
                opt.value = t.id;
                opt.textContent = t.name;
                og.appendChild(opt);
            });
            sel.appendChild(og);
        }
        sel.value = currentTemplate;
    }

    function compressImage(file, maxSize, quality) {
        return new Promise(function(resolve, reject) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const img = new Image();
                img.onload = function() {
                    let w = img.width;
                    let h = img.height;
                    if (w > maxSize || h > maxSize) {
                        const ratio = Math.min(maxSize / w, maxSize / h);
                        w = Math.round(w * ratio);
                        h = Math.round(h * ratio);
                    }
                    const canvas = document.createElement('canvas');
                    canvas.width = w;
                    canvas.height = h;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, w, h);
                    const base64 = canvas.toDataURL('image/jpeg', quality);
                    resolve({ base64: base64, width: w, height: h });
                };
                img.onerror = reject;
                img.src = e.target.result;
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    async function handleFiles(fileList) {
        const files = Array.from(fileList).filter(function(f) { return f.type.startsWith('image/'); });
        if (!files.length) {
            showToast('请选择图片文件', 'error');
            return;
        }

        let added = 0;
        for (const file of files) {
            try {
                const compressed = await compressImage(file, 1500, 0.82);
                const imgId = 'img_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5);
                images.push({
                    id: imgId,
                    filename: file.name,
                    base64: compressed.base64,
                    width: compressed.width,
                    height: compressed.height,
                    ratio_info: null,
                    preview: compressed.base64
                });
                added++;
            } catch (e) {
                showToast('图片加载失败: ' + file.name, 'error');
            }
        }

        renderImageList();
        showToast('已添加 ' + added + ' 张图片', 'success');
        analyzeImages();
        debouncePreview();
    }

    async function analyzeImages() {
        if (!images.length) return;

        const imageData = images.map(function(img) { return { base64: img.base64, filename: img.filename }; });
        try {
            const data = await api('/api/analyze', 'POST', { images: imageData });
            if (data.images) {
                data.images.forEach(function(info, idx) {
                    if (images[idx] && info.ratio_info) {
                        images[idx].ratio_info = info.ratio_info;
                    }
                });
                renderImageList();

                if (data.recommended_templates && data.recommended_templates.length && !images.length > 1) {
                    const rec = data.recommended_templates[0];
                    const sel = $('#templateSelect');
                    if (sel.value !== rec) {
                        for (const opt of sel.options) {
                            if (opt.value === rec) {
                                sel.value = rec;
                                currentTemplate = rec;
                                onTemplateChange();
                                break;
                            }
                        }
                    }
                }
            }
        } catch (e) {
            console.error('analyze error:', e);
        }
    }

    function renderImageList() {
        const list = $('#imageList');
        if (!images.length) {
            list.innerHTML = '<div class="empty-hint">暂无图片</div>';
            return;
        }

        list.innerHTML = images.map(function(img, idx) {
            const r = img.ratio_info || {};
            const ratioName = r.name || '';
            const device = r.device || '';
            return '<div class="image-item" draggable="true" data-id="' + img.id + '" data-index="' + idx + '">' +
                '<img class="thumb" src="' + img.preview + '" alt="">' +
                '<div class="info">' +
                '<div class="name">' + (img.filename || '图片' + (idx + 1)) + '</div>' +
                '<div class="meta">' + img.width + 'x' + img.height + ' ' + ratioName + ' ' + device + '</div>' +
                '</div>' +
                '<button class="remove-btn" data-id="' + img.id + '" title="移除">x</button>' +
                '</div>';
        }).join('');

        list.querySelectorAll('.remove-btn').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                removeImage(btn.dataset.id);
            });
        });

        setupDragSort();
    }

    function setupDragSort() {
        const list = $('#imageList');
        let dragEl = null;
        let dragIndex = -1;

        list.querySelectorAll('.image-item').forEach(function(item) {
            item.addEventListener('dragstart', function(e) {
                dragEl = item;
                dragIndex = parseInt(item.dataset.index);
                item.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
            });
            item.addEventListener('dragend', function() {
                item.classList.remove('dragging');
                dragEl = null;
            });
            item.addEventListener('dragover', function(e) {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
            });
            item.addEventListener('drop', function(e) {
                e.preventDefault();
                if (!dragEl || dragEl === item) return;
                const targetIdx = parseInt(item.dataset.index);
                reorderImages(dragIndex, targetIdx);
            });
        });
    }

    function reorderImages(fromIdx, toIdx) {
        const moved = images.splice(fromIdx, 1)[0];
        images.splice(toIdx, 0, moved);
        renderImageList();
        debouncePreview();
    }

    function removeImage(id) {
        images = images.filter(function(img) { return img.id !== id; });
        renderImageList();
        debouncePreview();
    }

    function getOptions() {
        const bgColor = $('#bgColor').value;
        const bgMode = $('#bgMode').value;
        const fitMode = $('#fitMode').value;
        const zoom = parseFloat($('#zoom').value);
        const offsetX = parseInt($('#offsetX').value);
        const offsetY = parseInt($('#offsetY').value);
        const showLockscreen = $('#showLockscreen').checked;
        const lockTime = $('#lockTime').value;
        const lockDate = $('#lockDate').value;
        const autoTextColor = $('#autoTextColor').checked;

        const brandMode = $('#brandMode').value;
        const brandName = $('#brandName').value;
        const subtitleText = $('#subtitleText').value;
        const brandOpacity = parseInt($('#brandOpacity').value);
        const brandColor = $('#brandColor').value;
        const subtitleColor = $('#subtitleColor').value;
        const watermarkText = $('#watermarkText').value;

        const outputWidth = parseInt($('#outputWidth').value) || 2400;
        const outputHeight = parseInt($('#outputHeight').value) || 2400;
        const outputFormat = $('#outputFormat').value;
        const outputQuality = parseInt($('#outputQuality').value);

        return {
            background_color: bgColor,
            bg_mode: bgMode,
            canvas_width: outputWidth,
            canvas_height: outputHeight,
            output_format: outputFormat,
            output_quality: outputQuality,
            device_options: {
                phone1: { fit_mode: fitMode, zoom: zoom, offset_x: offsetX, offset_y: offsetY },
                tablet1: { fit_mode: fitMode, zoom: zoom, offset_x: offsetX, offset_y: offsetY },
                desktop1: { fit_mode: fitMode, zoom: zoom, offset_x: offsetX, offset_y: offsetY },
                laptop1: { fit_mode: fitMode, zoom: zoom, offset_x: offsetX, offset_y: offsetY },
                monitor1: { fit_mode: fitMode, zoom: zoom, offset_x: offsetX, offset_y: offsetY },
            },
            lockscreen: {
                show: showLockscreen,
                show_time: true,
                show_date: true,
                time: lockTime,
                date: lockDate,
                auto_color: autoTextColor,
                text_shadow: true,
            },
            brand: {
                mode: brandMode,
                show_brand: brandName.trim().length > 0,
                name: brandName,
                subtitle: subtitleText,
                opacity: brandOpacity,
                brand_color: brandColor,
                subtitle_color: subtitleColor,
                watermark_text: watermarkText,
                align: 'center',
                uppercase_subtitle: true,
            }
        };
    }

    function debouncePreview() {
        clearTimeout(previewTimer);
        previewTimer = setTimeout(doPreview, 300);
    }

    async function doPreview() {
        if (!images.length) {
            $('#previewPlaceholder').style.display = 'block';
            $('#previewImage').style.display = 'none';
            return;
        }

        const imageData = images.map(function(img) { return { base64: img.base64, filename: img.filename }; });

        try {
            const data = await api('/api/preview', 'POST', {
                template_id: currentTemplate,
                images: imageData,
                options: getOptions()
            });

            if (data.success) {
                $('#previewPlaceholder').style.display = 'none';
                $('#previewImage').style.display = 'block';
                $('#previewImage').src = data.preview;
                $('#previewInfo').textContent = data.size.width + ' x ' + data.size.height;
            } else {
                showToast(data.error || '预览失败', 'error');
            }
        } catch (e) {
            showToast('预览失败: ' + e.message, 'error');
        }
    }

    async function generateImage() {
        if (!images.length) {
            showToast('请先上传图片', 'error');
            return;
        }

        const btn = $('#btnGenerate');
        btn.disabled = true;
        btn.textContent = '生成中...';

        try {
            const productName = $('#productName').value || 'wallpaper';
            const imageData = images.map(function(img) { return { base64: img.base64, filename: img.filename }; });

            const data = await api('/api/generate', 'POST', {
                template_id: currentTemplate,
                images: imageData,
                product_name: productName,
                options: getOptions()
            });

            if (data.success) {
                const link = document.createElement('a');
                link.href = data.image;
                link.download = data.filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);

                showToast('生成成功 ' + data.file_size_kb + ' KB', 'success');
                $('#generateResult').textContent = '已下载: ' + data.filename;
                $('#generateResult').classList.add('show');
                setTimeout(function() { $('#generateResult').classList.remove('show'); }, 5000);
            } else {
                showToast(data.error || '生成失败', 'error');
            }
        } catch (e) {
            showToast('生成失败: ' + e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = '💾 生成图片';
        }
    }

    function onTemplateChange() {
        const tpl = templates.find(function(t) { return t.id === currentTemplate; });
        if (tpl && tpl.default_canvas && canvasPresets[tpl.default_canvas]) {
            const preset = canvasPresets[tpl.default_canvas];
            currentCanvas = tpl.default_canvas;
            $('#canvasPreset').value = currentCanvas;
            $('#outputWidth').value = preset.width;
            $('#outputHeight').value = preset.height;
        }
        debouncePreview();
    }

    function onCanvasPresetChange() {
        const preset = canvasPresets[currentCanvas];
        if (preset) {
            $('#outputWidth').value = preset.width;
            $('#outputHeight').value = preset.height;
        }
        debouncePreview();
    }

    function onBrandModeChange() {
        const mode = $('#brandMode').value;
        $('#watermarkRow').style.display = mode === 'watermark' ? 'block' : 'none';
        debouncePreview();
    }

    function setupTabs() {
        $$('.tab-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                const tab = btn.dataset.tab;
                $$('.tab-btn').forEach(function(b) { b.classList.remove('active'); });
                $$('.tab-content').forEach(function(c) { c.classList.remove('active'); });
                btn.classList.add('active');
                $('#tab-' + tab).classList.add('active');
            });
        });
    }

    function setupDropZone() {
        const dz = $('#dropZone');
        const input = $('#fileInput');
        if (!dz || !input) return;

        dz.addEventListener('click', function() { input.click(); });
        input.addEventListener('change', function(e) {
            handleFiles(e.target.files);
            input.value = '';
        });

        ['dragenter', 'dragover'].forEach(function(ev) {
            dz.addEventListener(ev, function(e) { e.preventDefault(); dz.classList.add('drag-over'); });
        });

        ['dragleave', 'drop'].forEach(function(ev) {
            dz.addEventListener(ev, function(e) { e.preventDefault(); dz.classList.remove('drag-over'); });
        });

        dz.addEventListener('drop', function(e) {
            e.preventDefault();
            if (e.dataTransfer.files.length) { handleFiles(e.dataTransfer.files); }
        });

        document.addEventListener('dragover', function(e) { e.preventDefault(); });
        document.addEventListener('drop', function(e) { e.preventDefault(); });
    }

    function setupControls() {
        on('#templateSelect', 'change', function(e) {
            currentTemplate = e.target.value;
            onTemplateChange();
        });

        on('#canvasPreset', 'change', function(e) {
            currentCanvas = e.target.value;
            onCanvasPresetChange();
        });

        on('#bgColor', 'input', function(e) {
            $('#bgColorHex').value = e.target.value;
            debouncePreview();
        });

        on('#bgColorHex', 'change', function(e) {
            let val = e.target.value.trim();
            if (!val.startsWith('#')) val = '#' + val;
            $('#bgColor').value = val;
            debouncePreview();
        });

        $$('.bg-preset').forEach(function(p) {
            p.addEventListener('click', function() {
                const color = p.dataset.color;
                $('#bgColor').value = color;
                $('#bgColorHex').value = color;
                $$('.bg-preset').forEach(function(x) { x.classList.remove('active'); });
                p.classList.add('active');
                debouncePreview();
            });
        });

        on('#bgMode', 'change', debouncePreview);

        on('#brandMode', 'change', onBrandModeChange);

        on('#subtitlePreset', 'change', function(e) {
            if (e.target.value) {
                $('#subtitleText').value = e.target.value;
                debouncePreview();
            }
            e.target.value = '';
        });

        var controlIds = ['fitMode', 'zoom', 'offsetX', 'offsetY', 'showLockscreen', 'lockTime', 'lockDate',
             'autoTextColor', 'brandName', 'subtitleText', 'brandOpacity', 'brandColor', 'subtitleColor',
             'watermarkText', 'outputWidth', 'outputHeight', 'outputFormat', 'outputQuality'];

        controlIds.forEach(function(id) {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener('input', debouncePreview);
                el.addEventListener('change', debouncePreview);
            }
        });

        on('#zoom', 'input', function(e) { $('#zoomVal').textContent = parseFloat(e.target.value).toFixed(2) + 'x'; });
        on('#offsetX', 'input', function(e) { $('#offsetXVal').textContent = e.target.value + 'px'; });
        on('#offsetY', 'input', function(e) { $('#offsetYVal').textContent = e.target.value + 'px'; });
        on('#brandOpacity', 'input', function(e) { $('#brandOpacityVal').textContent = e.target.value + '%'; });
        on('#outputQuality', 'input', function(e) { $('#outputQualityVal').textContent = e.target.value; });

        on('#btnGenerate', 'click', generateImage);
        on('#btnReset', 'click', resetParams);
        on('#btnClearImages', 'click', clearImages);
    }

    function resetParams() {
        $('#bgColor').value = '#F5F2EB';
        $('#bgColorHex').value = '#F5F2EB';
        $('#bgMode').value = 'gradient';
        $$('.bg-preset').forEach(function(x, i) { x.classList.toggle('active', i === 0); });
        $('#fitMode').value = 'cover';
        $('#zoom').value = '1'; $('#zoomVal').textContent = '1.00x';
        $('#offsetX').value = '0'; $('#offsetXVal').textContent = '0px';
        $('#offsetY').value = '0'; $('#offsetYVal').textContent = '0px';
        $('#showLockscreen').checked = true;
        $('#lockTime').value = '9:42';
        $('#lockDate').value = '1月13日 星期一';
        $('#autoTextColor').checked = true;
        $('#brandMode').value = 'minimal';
        $('#watermarkRow').style.display = 'none';
        $('#brandName').value = '';
        $('#subtitleText').value = '';
        $('#brandOpacity').value = '45'; $('#brandOpacityVal').textContent = '45%';
        $('#brandColor').value = '#333333';
        $('#subtitleColor').value = '#888888';
        $('#outputFormat').value = 'JPEG';
        $('#outputQuality').value = '95'; $('#outputQualityVal').textContent = '95';
        $('#productName').value = 'wallpaper';
        onTemplateChange();
        showToast('参数已重置');
    }

    function clearImages() {
        if (!images.length) return;
        if (!confirm('确定清空所有图片吗？')) return;
        images = [];
        renderImageList();
        debouncePreview();
        showToast('已清空');
    }

    async function init() {
        setupTabs();
        setupDropZone();
        setupControls();
        await loadCanvasPresets();
        await loadTemplates();
        onTemplateChange();
        renderImageList();
    }

    document.addEventListener('DOMContentLoaded', init);
})();
