(function() {
    let templates = [];
    let images = [];
    let currentTemplate = 'single_phone';
    let previewTimer = null;

    function $(sel) { return document.querySelector(sel); }
    function $$(sel) { return document.querySelectorAll(sel); }
    function on(id, evt, cb) { const el = $(id); if (el) el.addEventListener(evt, cb); }

    function showToast(msg, type = '') {
        const t = $('#toast');
        t.textContent = msg;
        t.className = 'toast show ' + type;
        clearTimeout(t._timer);
        t._timer = setTimeout(() => {
            t.className = 'toast';
        }, 2500);
    }

    async function api(url, method = 'GET', data = null) {
        const opts = { method, headers: {} };
        if (data) {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(data);
        }
        const res = await fetch(url, opts);
        return await res.json();
    }

    async function loadTemplates() {
        const data = await api('/api/templates');
        templates = data.templates || [];
        const sel = $('#templateSelect');
        sel.innerHTML = '';
        templates.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.id;
            opt.textContent = t.name + ' (' + t.device_count + '台设备)';
            sel.appendChild(opt);
        });
        sel.value = currentTemplate;
    }

    function handleFiles(fileList) {
        const files = Array.from(fileList).filter(f => f.type.startsWith('image/'));
        if (!files.length) {
            showToast('请选择图片文件', 'error');
            return;
        }

        const formData = new FormData();
        files.forEach(f => formData.append('images', f));

        fetch('/api/upload', {
            method: 'POST',
            body: formData
        }).then(r => r.json()).then(data => {
            if (data.success) {
                images = data.images || [];
                renderImageList();
                showToast('上传成功 ' + data.uploaded_count + ' 张图片', 'success');
                debouncePreview();
            } else {
                showToast(data.error || '上传失败', 'error');
            }
        }).catch(e => {
            showToast('上传失败: ' + e.message, 'error');
        });
    }

    function renderImageList() {
        const list = $('#imageList');
        if (!images.length) {
            list.innerHTML = '<div class="empty-hint">暂无图片</div>';
            return;
        }

        list.innerHTML = images.map((img, idx) => {
            const r = img.ratio_info || {};
            const ratioName = r.name || '';
            const orient = r.orientation || '';
            const device = r.device || '';
            return `
                <div class="image-item" draggable="true" data-id="${img.id}" data-index="${idx}">
                    <img class="thumb" src="${img.preview}" alt="">
                    <div class="info">
                        <div class="name">${img.filename || '图片' + (idx + 1)}</div>
                        <div class="meta">${img.width}×${img.height} · ${ratioName} · ${device}</div>
                    </div>
                    <button class="remove-btn" data-id="${img.id}" title="移除">×</button>
                </div>
            `;
        }).join('');

        list.querySelectorAll('.remove-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
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

        list.querySelectorAll('.image-item').forEach(item => {
            item.addEventListener('dragstart', (e) => {
                dragEl = item;
                dragIndex = parseInt(item.dataset.index);
                item.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
            });

            item.addEventListener('dragend', () => {
                item.classList.remove('dragging');
                dragEl = null;
            });

            item.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
            });

            item.addEventListener('drop', (e) => {
                e.preventDefault();
                if (!dragEl || dragEl === item) return;
                const targetIdx = parseInt(item.dataset.index);
                reorderImages(dragIndex, targetIdx);
            });
        });
    }

    async function reorderImages(fromIdx, toIdx) {
        const order = images.map(img => img.id);
        const [moved] = order.splice(fromIdx, 1);
        order.splice(toIdx, 0, moved);

        const data = await api('/api/images/reorder', 'POST', { order });
        if (data.success) {
            images = data.images || [];
            renderImageList();
            debouncePreview();
        }
    }

    async function removeImage(id) {
        images = images.filter(img => img.id !== id);
        showToast('已移除图片');
        renderImageList();
        debouncePreview();
    }

    function getOptions() {
        const bgColor = $('#bgColor').value;
        const fitMode = $('#fitMode').value;
        const zoom = parseFloat($('#zoom').value);
        const offsetX = parseInt($('#offsetX').value);
        const offsetY = parseInt($('#offsetY').value);
        const showLockscreen = $('#showLockscreen').checked;
        const lockTime = $('#lockTime').value;
        const lockDate = $('#lockDate').value;
        const autoTextColor = $('#autoTextColor').checked;
        const textColor = $('#textColor').value;

        const showBrand = $('#showBrand').checked;
        const showSubtitle = $('#showSubtitle').checked;
        const brandName = $('#brandName').value;
        const subtitleText = $('#subtitleText').value;
        const brandSize = parseInt($('#brandSize').value);
        const subtitleSize = parseInt($('#subtitleSize').value);
        const letterSpacing = parseInt($('#letterSpacing').value);
        const lineSpacing = parseInt($('#lineSpacing').value);
        const textAlign = $('#textAlign').value;
        const brandColor = $('#brandColor').value;
        const subtitleColor = $('#subtitleColor').value;
        const textStyle = $('#textStyle').value;

        const outputWidth = parseInt($('#outputWidth').value);
        const outputHeight = parseInt($('#outputHeight').value);
        const outputFormat = $('#outputFormat').value;
        const outputQuality = parseInt($('#outputQuality').value);
        const minFileSize = parseInt($('#minFileSize').value) || 0;

        return {
            background_color: bgColor,
            canvas_width: outputWidth,
            canvas_height: outputHeight,
            output_format: outputFormat,
            output_quality: outputQuality,
            min_file_size_kb: minFileSize,
            device_options: {
                phone1: {
                    fit_mode: fitMode,
                    zoom: zoom,
                    offset_x: offsetX,
                    offset_y: offsetY,
                }
            },
            lockscreen: {
                show: showLockscreen,
                show_time: true,
                show_date: true,
                time: lockTime,
                date: lockDate,
                auto_color: autoTextColor,
                text_color: textColor,
                text_shadow: true,
            },
            brand: {
                show_brand: showBrand,
                show_subtitle: showSubtitle,
                name: brandName,
                subtitle: subtitleText,
                brand_size: brandSize,
                subtitle_size: subtitleSize,
                brand_color: brandColor,
                subtitle_color: subtitleColor,
                align: textAlign,
                letter_spacing: letterSpacing,
                line_spacing: lineSpacing,
                text_style: textStyle,
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

        const data = await api('/api/preview', 'POST', {
            template_id: currentTemplate,
            options: getOptions()
        });

        if (data.success) {
            $('#previewPlaceholder').style.display = 'none';
            $('#previewImage').style.display = 'block';
            $('#previewImage').src = data.preview;
            $('#previewInfo').textContent = data.size.width + ' × ' + data.size.height;
        } else {
            showToast(data.error || '预览失败', 'error');
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
            const data = await api('/api/generate', 'POST', {
                template_id: currentTemplate,
                product_name: productName,
                options: getOptions()
            });

            if (data.success) {
                showToast('生成成功！大小: ' + data.file_size_kb + ' KB', 'success');
                $('#generateResult').textContent = '已保存到: ' + data.output_path;
                $('#generateResult').classList.add('show');
                setTimeout(() => {
                    $('#generateResult').classList.remove('show');
                }, 5000);
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

    function setupTabs() {
        $$('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const tab = btn.dataset.tab;
                $$('.tab-btn').forEach(b => b.classList.remove('active'));
                $$('.tab-content').forEach(c => c.classList.remove('active'));
                btn.classList.add('active');
                $('#tab-' + tab).classList.add('active');
            });
        });
    }

    function setupDropZone() {
        const dz = $('#dropZone');
        const input = $('#fileInput');

        if (!dz || !input) return;

        dz.addEventListener('click', () => input.click());
        input.addEventListener('change', (e) => {
            handleFiles(e.target.files);
            input.value = '';
        });

        ['dragenter', 'dragover'].forEach(ev => {
            dz.addEventListener(ev, (e) => {
                e.preventDefault();
                dz.classList.add('drag-over');
            });
        });

        ['dragleave', 'drop'].forEach(ev => {
            dz.addEventListener(ev, (e) => {
                e.preventDefault();
                dz.classList.remove('drag-over');
            });
        });

        dz.addEventListener('drop', (e) => {
            e.preventDefault();
            if (e.dataTransfer.files.length) {
                handleFiles(e.dataTransfer.files);
            }
        });

        document.addEventListener('dragover', (e) => e.preventDefault());
        document.addEventListener('drop', (e) => e.preventDefault());
    }

    function setupControls() {
        try {
            on('#templateSelect', 'change', (e) => {
                currentTemplate = e.target.value;
                debouncePreview();
            });

        on('#bgColor', 'input', (e) => {
            $('#bgColorHex').value = e.target.value;
            debouncePreview();
        });

        on('#bgColorHex', 'change', (e) => {
            let val = e.target.value.trim();
            if (!val.startsWith('#')) val = '#' + val;
            $('#bgColor').value = val;
            debouncePreview();
        });

        $$('.color-pres').forEach(p => {
            p.addEventListener('click', () => {
                const color = p.dataset.color;
                $('#bgColor').value = color;
                $('#bgColorHex').value = color;
                $$('.color-pres').forEach(x => x.classList.remove('active'));
                p.classList.add('active');
                debouncePreview();
            });
        });

        ['fitMode', 'zoom', 'offsetX', 'offsetY', 'showLockscreen', 'lockTime', 'lockDate',
         'autoTextColor', 'textColor', 'showBrand', 'showSubtitle', 'brandName',
         'subtitleText', 'brandSize', 'subtitleSize', 'letterSpacing', 'lineSpacing',
         'textAlign', 'textStyle', 'brandColor', 'subtitleColor', 'outputWidth', 'outputHeight',
         'outputFormat', 'outputQuality'].forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener('input', debouncePreview);
                el.addEventListener('change', debouncePreview);
            }
        });

        on('#zoom', 'input', (e) => {
            $('#zoomVal').textContent = parseFloat(e.target.value).toFixed(2) + 'x';
        });
        on('#offsetX', 'input', (e) => {
            $('#offsetXVal').textContent = e.target.value + 'px';
        });
        on('#offsetY', 'input', (e) => {
            $('#offsetYVal').textContent = e.target.value + 'px';
        });
        on('#brandSize', 'input', (e) => {
            $('#brandSizeVal').textContent = e.target.value + 'px';
        });
        on('#subtitleSize', 'input', (e) => {
            $('#subtitleSizeVal').textContent = e.target.value + 'px';
        });
        on('#letterSpacing', 'input', (e) => {
            $('#letterSpacingVal').textContent = e.target.value + 'px';
        });
        on('#lineSpacing', 'input', (e) => {
            $('#lineSpacingVal').textContent = e.target.value + 'px';
        });
        on('#outputQuality', 'input', (e) => {
            $('#outputQualityVal').textContent = e.target.value;
        });

        on('#canvasRatio', 'change', (e) => {
            const opt = e.target.options[e.target.selectedIndex];
            const w = opt.dataset.width;
            const h = opt.dataset.height;
            if (w && h) {
                $('#outputWidth').value = w;
                $('#outputHeight').value = h;
                debouncePreview();
            }
        });

        on('#autoTextColor', 'change', (e) => {
            $('#textColorRow').style.display = e.target.checked ? 'none' : 'block';
        });

        on('#subtitlePreset', 'change', (e) => {
            if (e.target.value) {
                $('#subtitleText').value = e.target.value;
                debouncePreview();
            }
            e.target.value = '';
        });

        on('#btnGenerate', 'click', generateImage);
        on('#btnReset', 'click', resetParams);
        on('#btnClearImages', 'click', clearImages);

        on('#btnOpenInput', 'click', async () => {
            await api('/api/input/open', 'POST');
        });
        on('#btnOpenOutput', 'click', async () => {
            await api('/api/output/open', 'POST');
        });

        on('#btnStartWatcher', 'click', startWatcher);
        on('#btnStopWatcher', 'click', stopWatcher);

        on('#btnBatchScan', 'click', batchScan);
        on('#btnBatchRun', 'click', batchRun);
        } catch (err) {
            console.error('setupControls error:', err);
        }
    }

    function resetParams() {
        $('#bgColor').value = '#F5F2EB';
        $('#bgColorHex').value = '#F5F2EB';
        $('#fitMode').value = 'cover';
        $('#zoom').value = '1';
        $('#zoomVal').textContent = '1.00x';
        $('#offsetX').value = '0';
        $('#offsetXVal').textContent = '0px';
        $('#offsetY').value = '0';
        $('#offsetYVal').textContent = '0px';
        $('#showLockscreen').checked = true;
        $('#lockTime').value = '9:42';
        $('#lockDate').value = '1月13日 星期一';
        $('#autoTextColor').checked = true;
        $('#textColorRow').style.display = 'none';
        $('#showBrand').checked = true;
        $('#showSubtitle').checked = true;
        $('#brandName').value = '米草科技';
        $('#subtitleText').value = 'PHONE WALLPAPER';
        $('#brandSize').value = '48';
        $('#brandSizeVal').textContent = '48px';
        $('#subtitleSize').value = '22';
        $('#subtitleSizeVal').textContent = '22px';
        $('#letterSpacing').value = '3';
        $('#letterSpacingVal').textContent = '3px';
        $('#lineSpacing').value = '12';
        $('#lineSpacingVal').textContent = '12px';
        $('#textAlign').value = 'center';
        $('#textStyle').value = 'minimal';
        $('#brandColor').value = '#333333';
        $('#subtitleColor').value = '#888888';
        $('#canvasRatio').value = '3:4';
        $('#outputWidth').value = '1500';
        $('#outputHeight').value = '2000';
        $('#outputFormat').value = 'JPEG';
        $('#outputQuality').value = '95';
        $('#outputQualityVal').textContent = '95';
        $('#minFileSize').value = '0';
        debouncePreview();
        showToast('参数已重置');
    }

    async function clearImages() {
        if (!images.length) return;
        if (!confirm('确定清空所有图片吗？')) return;
        await api('/api/images/clear', 'POST');
        images = [];
        renderImageList();
        debouncePreview();
        showToast('已清空');
    }

    async function startWatcher() {
        const data = await api('/api/watcher/start', 'POST');
        if (data.success) {
            updateWatcherStatus(true);
            showToast('文件夹监听已启动', 'success');
        }
    }

    async function stopWatcher() {
        const data = await api('/api/watcher/stop', 'POST');
        if (data.success) {
            updateWatcherStatus(false);
            showToast('文件夹监听已停止');
        }
    }

    function updateWatcherStatus(running) {
        const dot = $('#watcherDot');
        const text = $('#watcherText');
        const startBtn = $('#btnStartWatcher');
        const stopBtn = $('#btnStopWatcher');

        if (running) {
            dot.className = 'status-dot status-on';
            text.textContent = '运行中';
            startBtn.disabled = true;
            stopBtn.disabled = false;
        } else {
            dot.className = 'status-dot status-off';
            text.textContent = '未启动';
            startBtn.disabled = false;
            stopBtn.disabled = true;
        }
    }

    async function batchScan() {
        const data = await api('/api/batch/scan');
        if (data.products && data.products.length) {
            showToast('发现 ' + data.products.length + ' 个商品/图片', 'success');
            $('#batchResult').textContent = '发现 ' + data.products.length + ' 个商品，点击批量生成开始处理';
            $('#batchResult').classList.add('show');
        } else {
            showToast('input 目录为空');
            $('#batchResult').textContent = 'input 目录为空，请先放入图片';
            $('#batchResult').classList.add('show');
        }
    }

    async function batchRun() {
        const btn = $('#btnBatchRun');
        btn.disabled = true;
        btn.textContent = '处理中...';

        try {
            const data = await api('/api/batch/run', 'POST', { options: getOptions() });
            if (data.success) {
                const okCount = data.results.filter(r => r.success).length;
                showToast('批量处理完成: ' + okCount + '/' + data.results.length, 'success');
                $('#batchResult').textContent = '完成！成功 ' + okCount + '/' + data.results.length;
                $('#batchResult').classList.add('show');
            } else {
                showToast(data.error || '批量处理失败', 'error');
            }
        } catch (e) {
            showToast('批量处理失败: ' + e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = '批量生成';
        }
    }

    async function init() {
        setupTabs();
        setupDropZone();
        setupControls();
        await loadTemplates();
        updateWatcherStatus(false);
        renderImageList();
    }

    document.addEventListener('DOMContentLoaded', init);
})();
