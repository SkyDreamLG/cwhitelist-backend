/* ============================================================
   CWhitelist - 侧边栏交互脚本
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

    // ==================== DOM 元素 ====================
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebarToggleBtnText = sidebarToggle ? sidebarToggle.querySelector('.sidebar-toggle-text') : null;
    const sidebarToggleMobile = document.getElementById('sidebarToggleMobile');
    const sidebarClose = document.getElementById('sidebarClose');

    // ==================== 保存侧边栏状态到 localStorage ====================
    function saveSidebarState(collapsed) {
        try {
            localStorage.setItem('sidebar-collapsed', collapsed ? 'true' : 'false');
        } catch (e) { /* 忽略 */ }
    }

    function loadSidebarState() {
        try {
            return localStorage.getItem('sidebar-collapsed') === 'true';
        } catch (e) {
            return false;
        }
    }

    // ==================== 桌面端：切换侧边栏折叠/展开 ====================
    if (sidebar && sidebarToggle) {
        // 恢复上次状态
        if (loadSidebarState()) {
            sidebar.classList.add('collapsed');
        }

        sidebarToggle.addEventListener('click', function (e) {
            e.stopPropagation();
            sidebar.classList.toggle('collapsed');
            const isCollapsed = sidebar.classList.contains('collapsed');
            saveSidebarState(isCollapsed);

            // 更新按钮图标方向
            const icon = sidebarToggle.querySelector('i');
            if (icon) {
                if (isCollapsed) {
                    icon.classList.remove('bi-chevron-bar-left');
                    icon.classList.add('bi-chevron-bar-right');
                } else {
                    icon.classList.remove('bi-chevron-bar-right');
                    icon.classList.add('bi-chevron-bar-left');
                }
            }
        });

        // 初始化图标
        if (sidebar.classList.contains('collapsed')) {
            const icon = sidebarToggle.querySelector('i');
            if (icon) {
                icon.classList.remove('bi-chevron-bar-left');
                icon.classList.add('bi-chevron-bar-right');
            }
        }
    }

    // ==================== 移动端：打开/关闭侧边栏 ====================
    function openSidebarMobile() {
        if (sidebar) {
            sidebar.classList.add('mobile-show');
            sidebar.classList.remove('collapsed');
        }
        if (sidebarOverlay) {
            sidebarOverlay.classList.add('show');
        }
        document.body.style.overflow = 'hidden';
    }

    function closeSidebarMobile() {
        if (sidebar) {
            sidebar.classList.remove('mobile-show');
        }
        if (sidebarOverlay) {
            sidebarOverlay.classList.remove('show');
        }
        document.body.style.overflow = '';
    }

    if (sidebarToggleMobile) {
        sidebarToggleMobile.addEventListener('click', function (e) {
            e.stopPropagation();
            if (sidebar && sidebar.classList.contains('mobile-show')) {
                closeSidebarMobile();
            } else {
                openSidebarMobile();
            }
        });
    }

    if (sidebarClose) {
        sidebarClose.addEventListener('click', function (e) {
            e.stopPropagation();
            closeSidebarMobile();
        });
    }

    // 点击遮罩层关闭
    if (sidebarOverlay) {
        sidebarOverlay.addEventListener('click', function () {
            closeSidebarMobile();
        });
    }

    // 按 ESC 关闭
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && sidebar && sidebar.classList.contains('mobile-show')) {
            closeSidebarMobile();
        }
    });

    // ==================== 窗口大小改变时处理 ====================
    let lastWindowWidth = window.innerWidth;
    window.addEventListener('resize', function () {
        const currentWidth = window.innerWidth;
        // 从移动端切换到桌面端时，关闭移动端侧边栏
        if (lastWindowWidth <= 991 && currentWidth > 991) {
            closeSidebarMobile();
        }
        lastWindowWidth = currentWidth;
    });

    // ==================== 子菜单展开时保持同级只有一个打开 ====================
    const submenuToggles = sidebar ? sidebar.querySelectorAll('[data-bs-toggle="collapse"]') : [];
    submenuToggles.forEach(function (toggle) {
        toggle.addEventListener('click', function () {
            // 在折叠模式下点击展开的子菜单，先展开侧边栏
            if (sidebar && sidebar.classList.contains('collapsed') && !sidebar.classList.contains('mobile-show')) {
                sidebar.classList.remove('collapsed');
                saveSidebarState(false);
                const icon = sidebarToggle ? sidebarToggle.querySelector('i') : null;
                if (icon) {
                    icon.classList.remove('bi-chevron-bar-right');
                    icon.classList.add('bi-chevron-bar-left');
                }
                // 短暂延迟后显示子菜单
                const targetId = toggle.getAttribute('href');
                setTimeout(function () {
                    const target = document.querySelector(targetId);
                    if (target && !target.classList.contains('show')) {
                        // BS collapse API
                        const bsCollapse = new bootstrap.Collapse(target, {toggle: true});
                    }
                }, 300);
            }
        });
    });

    // ==================== 自动解除 alert ====================
    const autoDismissAlerts = document.querySelectorAll('.alert-dismissible');
    autoDismissAlerts.forEach(function (alert) {
        setTimeout(function () {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) {
                bsAlert.close();
            }
        }, 5000);
    });

    // ==================== 确认删除对话框 ====================
    const confirmDeleteLinks = document.querySelectorAll('[data-confirm]');
    confirmDeleteLinks.forEach(function (link) {
        link.addEventListener('click', function (e) {
            const message = link.getAttribute('data-confirm') || 'Are you sure?';
            if (!confirm(message)) {
                e.preventDefault();
                e.stopPropagation();
            }
        });
    });

    // ==================== active 菜单判断附加逻辑 ====================
    // 确保 JS 端的路由高亮也能正常工作（作为 Jinja2 判断的补充）
    (function highlightCurrentPath() {
        if (!sidebar) return;
        const currentPath = window.location.pathname;
        const navLinks = sidebar.querySelectorAll('.nav-link');
        navLinks.forEach(function (link) {
            const href = link.getAttribute('href');
            // 跳过子菜单切换和 # 链接
            if (!href || href.startsWith('#') || href.includes('collapse')) return;

            // 完全匹配或前缀匹配（处理带参数的 URL）
            if (href === currentPath ||
                (href !== '/' && currentPath.startsWith(href + '?'))) {
                // 如果已有 Jinja2 active，此处额外确保
                link.classList.add('active');
            }
        });
    })();

});

// ==================== 滚动位置保存与恢复 ====================
// 解决表单 onchange="submit()" 导致页面弹到顶部的问题
(function() {
    // 页面加载时恢复滚动
    var state = sessionStorage.getItem('_scrollState');
    if (state) {
        try {
            var data = JSON.parse(state);
            // 仅当是同一页面（路径相同）时恢复滚动，跨页面导航不恢复
            if (data.path === window.location.pathname) {
                window.scrollTo(0, data.y || 0);
            }
        } catch(e) {}
        sessionStorage.removeItem('_scrollState');
    }

    // 离开页面前保存滚动位置和路径
    window.addEventListener('beforeunload', function() {
        sessionStorage.setItem('_scrollState', JSON.stringify({
            path: window.location.pathname,
            y: window.scrollY
        }));
    });
})();

// ==================== 全局函数：切换语言 ====================
function switchLanguage(langCode) {
    fetch('/set-language', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: 'lang=' + encodeURIComponent(langCode)
    })
    .then(function(response) {
        return response.json();
    })
    .then(function(data) {
        if (data.success) {
            // 刷新当前页面以应用新语言
            window.location.reload();
        } else {
            console.error('Language switch failed:', data.error);
        }
    })
    .catch(function(error) {
        console.error('Language switch error:', error);
        // 兜底：直接刷新页面（后端可能从 URL 参数获取）
        window.location.href = window.location.pathname + '?lang=' + langCode;
    });
}