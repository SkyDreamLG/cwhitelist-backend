// 主JavaScript文件

$(document).ready(function() {
    // 初始化工具提示
    $('[data-bs-toggle="tooltip"]').tooltip();

    // 初始化弹出框
    $('[data-bs-toggle="popover"]').popover();

    // 自动消失的警报
    $('.alert-auto-dismiss').delay(5000).fadeOut('slow');

    // 表单提交确认
    $('form[data-confirm]').on('submit', function(e) {
        const message = $(this).data('confirm') || '确定要执行此操作吗？';
        if (!confirm(message)) {
            e.preventDefault();
            return false;
        }
        return true;
    });

    // 批量操作复选框
    $('#selectAll').on('change', function() {
        $('.select-item').prop('checked', $(this).prop('checked'));
    });

    // 实时搜索
    $('.search-input').on('keyup', function() {
        const search = $(this).val().toLowerCase();
        const table = $(this).closest('.card').find('table');

        table.find('tbody tr').each(function() {
            const text = $(this).text().toLowerCase();
            $(this).toggle(text.includes(search));
        });
    });

    // 日期选择器
    $('.date-picker').each(function() {
        $(this).attr('type', 'date');
    });

    // API测试功能
    $('.test-api').on('click', function(e) {
        e.preventDefault();
        const endpoint = $(this).data('endpoint');
        const method = $(this).data('method') || 'GET';
        const token = $('#apiToken').val();

        if (!token && endpoint !== '/api/health') {
            alert('请输入API令牌');
            return;
        }

        $.ajax({
            url: endpoint,
            method: method,
            headers: token ? { 'Authorization': 'Bearer ' + token } : {},
            success: function(response) {
                $('#apiResult').text(JSON.stringify(response, null, 2));
                $('#apiModal').modal('show');
            },
            error: function(xhr) {
                $('#apiResult').text(JSON.stringify(xhr.responseJSON || { error: xhr.statusText }, null, 2));
                $('#apiModal').modal('show');
            }
        });
    });

    // 复制到剪贴板
    $('.copy-to-clipboard').on('click', function() {
        const text = $(this).data('text') || $(this).prev('input').val();

        navigator.clipboard.writeText(text).then(function() {
            const $btn = $(this);
            const original = $btn.html();
            $btn.html('<i class="fas fa-check"></i> 已复制');
            setTimeout(function() {
                $btn.html(original);
            }, 2000);
        }.bind(this)).catch(function(err) {
            console.error('复制失败: ', err);
            alert('复制失败，请手动复制');
        });
    });

    // 数据表格增强
    $('.data-table').each(function() {
        const $table = $(this);
        const $search = $table.closest('.card').find('.table-search');

        if ($search.length) {
            $search.on('keyup', function() {
                const value = $(this).val().toLowerCase();
                $table.find('tbody tr').filter(function() {
                    $(this).toggle($(this).text().toLowerCase().indexOf(value) > -1);
                });
            });
        }
    });

    // 自动刷新仪表板
    if (window.location.pathname === '/dashboard') {
        setInterval(function() {
            $.get('/api/stats', function(data) {
                if (data.success) {
                    // 更新统计数据
                    $('#totalEntries').text(data.stats.whitelist.total);
                    $('#activeEntries').text(data.stats.whitelist.active);
                }
            });
        }, 30000); // 每30秒刷新一次
    }

    // 平滑滚动
    $('a[href^="#"]').on('click', function(e) {
        if (this.hash !== '') {
            e.preventDefault();
            const hash = this.hash;
            $('html, body').animate({
                scrollTop: $(hash).offset().top - 70
            }, 800);
        }
    });

    // 实时通知（WebSocket示例）
    if (typeof io !== 'undefined') {
        const socket = io();

        socket.on('whitelist_update', function(data) {
            showNotification('白名单已更新', data.message || '白名单条目有变更', 'info');
        });

        socket.on('server_status', function(data) {
            showNotification('服务器状态变更', data.server + ': ' + data.status, 'warning');
        });

        socket.on('login_event', function(data) {
            if (!data.allowed) {
                showNotification('登录被拒绝', data.player + ' 尝试登录被拒绝', 'danger');
            }
        });
    }

    // 显示通知
    function showNotification(title, message, type) {
        const notification = $(
            '<div class="toast" role="alert" aria-live="assertive" aria-atomic="true">' +
            '<div class="toast-header">' +
            '<strong class="me-auto">' + title + '</strong>' +
            '<small class="text-muted">刚刚</small>' +
            '<button type="button" class="btn-close" data-bs-dismiss="toast"></button>' +
            '</div>' +
            '<div class="toast-body">' + message + '</div>' +
            '</div>'
        );

        notification.addClass('bg-' + type + ' text-white');
        $('#notificationContainer').append(notification);

        const toast = new bootstrap.Toast(notification[0]);
        toast.show();

        // 自动移除
        setTimeout(function() {
            notification.remove();
        }, 5000);
    }

    // 导出功能
    $('.export-btn').on('click', function() {
        const format = $(this).data('format') || 'json';
        const endpoint = $(this).data('endpoint');

        $.ajax({
            url: endpoint + '?format=' + format,
            method: 'GET',
            headers: { 'Authorization': 'Bearer ' + $('#apiToken').val() },
            success: function(data) {
                let content, mime, filename;

                if (format === 'json') {
                    content = JSON.stringify(data, null, 2);
                    mime = 'application/json';
                    filename = 'export.json';
                } else if (format === 'csv') {
                    content = convertToCSV(data);
                    mime = 'text/csv';
                    filename = 'export.csv';
                }

                downloadFile(content, filename, mime);
            }
        });
    });

    function convertToCSV(data) {
        // 简单的CSV转换
        const array = typeof data !== 'object' ? JSON.parse(data) : data;
        let str = '';

        // 标题行
        if (array.length > 0) {
            str += Object.keys(array[0]).join(',') + '\r\n';
        }

        // 数据行
        array.forEach(item => {
            str += Object.values(item).join(',') + '\r\n';
        });

        return str;
    }

    function downloadFile(content, filename, mime) {
        const blob = new Blob([content], { type: mime });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
});