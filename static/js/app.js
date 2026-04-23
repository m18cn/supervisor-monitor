(function ($) {
    'use strict';

    const Utils = window.SuperMonitorUtils;
    const API = window.SuperMonitorAPI;
    if (!Utils || !API) {
        console.error('依赖 utils.js 和 api.js 未加载');
        return;
    }

    const POLL_INTERVAL = 4000;
    const MAX_POLL_INTERVAL = 30000;
    const PAGE_SIZE = 10;
    let pollTimer = null;
    let pollingActive = false;
    let pollInFlight = false;
    let pollFailureCount = 0;
    let deleteTargetName = null;
    let lastProcessList = [];
    let currentPage = 1;

    function getStatusClass(statename) {
        const s = (statename || '').toUpperCase();
        if (s === 'RUNNING') return 'status-running';
        if (s === 'STOPPED' || s === 'EXITED') return 'status-stopped';
        if (s === 'STARTING' || s === 'STOPPING') return 'status-starting';
        return 'status-unknown';
    }

    function renderProcessTable(processes) {
        const tbody = $('#process-tbody');
        if (!processes || processes.length === 0) {
            tbody.html('<tr class="empty-row"><td colspan="10">暂无守护进程</td></tr>');
            $('#pagination-wrap').addClass('hidden');
            return;
        }
        const totalPages = Math.ceil(processes.length / PAGE_SIZE);
        if (currentPage > totalPages) currentPage = totalPages || 1;
        const start = (currentPage - 1) * PAGE_SIZE;
        const pageData = processes.slice(start, start + PAGE_SIZE);

        const rows = pageData.map(function (p) {
            const groupName = p.group || p.name;
            const statusClass = getStatusClass(p.statename);
            const pid = p.pid || '-';
            const count = p.count || 1;
            const priority = p.priority || 999;
            const user = p.user || '-';
            const location = p.stdout_logfile ? Utils.escapeHtml(p.stdout_logfile) : '-';

            const safeName = Utils.escapeAttr(groupName);
            const logName = p.log_process_name || groupName;
            const safeLogName = Utils.escapeAttr(logName);
            const isRunning = (p.statename || '').toUpperCase() === 'RUNNING';
            const statusText = isRunning ? '运行中' : '未启动';
            const statusCls = isRunning ? 'mgmt-running' : 'mgmt-stopped';
            const processMgmt = '<span class="status-trigger ' + statusCls + '" data-name="' + safeName + '" title="点击管理进程">' + statusText + '</span>';
            const pidDisplay = pid !== '-' ? '<span class="pid-trigger" data-pid="' + Utils.escapeAttr(String(pid)) + '" title="点击查看">查看</span>' : '-';
            const actions = '<button class="btn btn-outline btn-sm btn-edit" data-name="' + safeName + '">编辑</button>' +
                '<button class="btn btn-outline btn-sm btn-log" data-name="' + safeName + '" data-log-name="' + safeLogName + '">日志</button>' +
                '<button class="btn btn-outline btn-sm btn-danger btn-delete" data-name="' + safeName + '">删除</button>';

            return '<tr>' +
                '<td>' + Utils.escapeHtml(groupName) + '</td>' +
                '<td>' + Utils.escapeHtml(user) + '</td>' +
                '<td>' + pidDisplay + '</td>' +
                '<td>' + count + '</td>' +
                '<td>' + priority + '</td>' +
                '<td><div class="action-btns">' + processMgmt + '</div></td>' +
                '<td><span class="status-badge ' + statusClass + '">' + Utils.escapeHtml(p.statename || 'UNKNOWN') + '</span></td>' +
                '<td title="' + location + '">' + (location.length > 30 ? Utils.escapeHtml(location.substring(0, 27)) + '...' : location) + '</td>' +
                '<td><button class="btn btn-outline btn-sm btn-config" data-name="' + safeName + '">查看</button></td>' +
                '<td><div class="action-btns">' + actions + '</div></td>' +
                '</tr>';
        }).join('');

        tbody.html(rows);
        renderPagination(processes.length, totalPages);
    }

    function renderPagination(total, totalPages) {
        const $wrap = $('#pagination-wrap');
        if (totalPages <= 1) {
            $wrap.addClass('hidden');
            return;
        }
        $wrap.removeClass('hidden');
        let html = '<span class="pagination-info">' + total + ' 条，第 ' + currentPage + '/' + totalPages + ' 页</span>';
        html += '<button type="button" class="btn btn-outline btn-sm btn-page-prev" ' + (currentPage <= 1 ? 'disabled' : '') + '>上一页</button>';
        html += '<button type="button" class="btn btn-outline btn-sm btn-page-next" ' + (currentPage >= totalPages ? 'disabled' : '') + '>下一页</button>';
        $wrap.html(html);
    }

    function updateStats(processes) {
        const total = processes ? processes.length : 0;
        const running = processes ? processes.filter(function (p) {
            return (p.statename || '').toUpperCase() === 'RUNNING';
        }).length : 0;
        const stopped = total - running;

        $('#stat-total').text(total);
        $('#stat-running').text(running);
        $('#stat-stopped').text(stopped);
    }

    function updateSupervisorStatus() {
        API.getSupervisorState().done(function (res) {
            if (res.success && res.data) {
                const state = res.data.statename || res.data;
                $('#service-status').text(state).removeClass('status-running status-stopped').addClass('status-' + (state === 'RUNNING' ? 'running' : 'stopped'));
            } else {
                $('#service-status').text('连接失败').addClass('status-stopped');
            }
        }).fail(function (xhr) {
            $('#service-status').text(Utils.getApiError(xhr, '连接失败')).addClass('status-stopped');
        });
    }

    function loadLogContent(res, fallback) {
        return res.success ? res.data : (res.message || fallback || '加载失败');
    }

    function checkLogAnomaly(content) {
        const $alert = $('#log-anomaly-alert');
        if (!content || typeof content !== 'string') {
            $alert.addClass('hidden').text('');
            return;
        }
        if (content.indexOf('Could not open input file') !== -1) {
            $alert.removeClass('hidden').text('检测到异常：PHP 无法找到脚本文件，请检查 command 中的路径是否正确。');
            return;
        }
        if (content.indexOf('Permission denied') !== -1 || content.indexOf('No such file') !== -1) {
            $alert.removeClass('hidden').text('检测到异常：权限不足或文件不存在，请检查路径和用户权限。');
            return;
        }
        $alert.addClass('hidden').text('');
    }

    function loadLog(tab) {
        if (tab === 'service') {
            $('#runtime-log-selector').addClass('hidden');
            API.getMainLog().done(function (res) {
                const content = loadLogContent(res, '加载失败');
                $('#log-content').text(content);
                checkLogAnomaly(content);
            });
        } else {
            $('#runtime-log-selector').removeClass('hidden');
            const $sel = $('#runtime-process-select');
            $sel.empty().append('<option value="">-- 请选择进程 --</option>');
            lastProcessList.forEach(function (p) {
                const displayName = p.group || p.name;
                const logName = p.log_process_name || displayName;
                $sel.append('<option value="' + Utils.escapeAttr(logName) + '">' + Utils.escapeHtml(displayName) + '</option>');
            });
            $sel.off('change').on('change', function () {
                const name = $(this).val();
                if (name) {
                    API.getProcessLog(name).done(function (res) {
                        const content = loadLogContent(res, '加载失败');
                        $('#log-content').text(content);
                        checkLogAnomaly(content);
                    });
                } else {
                    $('#log-content').text('请选择进程查看运行日志');
                    checkLogAnomaly('');
                }
            });
            const first = lastProcessList[0];
            if (first) {
                const logName = first.log_process_name || first.group || first.name;
                $sel.val(logName);
                API.getProcessLog(logName).done(function (res) {
                    const content = loadLogContent(res, '加载失败');
                    $('#log-content').text(content);
                    checkLogAnomaly(content);
                });
            } else {
                $('#log-content').text('暂无进程，请先添加守护进程');
                checkLogAnomaly('');
            }
        }
    }

    function getBackoffInterval() {
        // 失败时指数退避：4s -> 8s -> 16s -> 30s(max)
        const step = Math.min(pollFailureCount, 3);
        return Math.min(POLL_INTERVAL * Math.pow(2, step), MAX_POLL_INTERVAL);
    }

    function scheduleNextPoll(customDelay) {
        if (!pollingActive) return;
        if (pollTimer) {
            clearTimeout(pollTimer);
        }
        const delay = (typeof customDelay === 'number') ? customDelay : getBackoffInterval();
        pollTimer = setTimeout(function () {
            pollTimer = null;
            fetchAndRenderStatus();
        }, delay);
    }

    function fetchAndRenderStatus() {
        if (pollInFlight) {
            return;
        }
        pollInFlight = true;
        API.getStatus()
            .done(function (res) {
                if (res.success && res.data) {
                    pollFailureCount = 0;
                    lastProcessList = res.data;
                    renderProcessTable(lastProcessList);
                    updateStats(lastProcessList);
                    updateSupervisorStatus();
                } else {
                    pollFailureCount += 1;
                    $('#process-tbody').html('<tr class="empty-row"><td colspan="5">获取状态失败: ' + Utils.escapeHtml(res.message || '未知错误') + '</td></tr>');
                }
            })
            .fail(function (xhr) {
                if (xhr.status === 401) {
                    showLoginPanel();
                    stopPolling();
                } else {
                    pollFailureCount += 1;
                    const msg = Utils.getApiError(xhr, '请求失败，请检查网络');
                    $('#process-tbody').html('<tr class="empty-row"><td colspan="5">获取状态失败: ' + Utils.escapeHtml(msg) + '</td></tr>');
                }
            })
            .always(function () {
                pollInFlight = false;
                if (pollingActive) {
                    scheduleNextPoll();
                }
            });
    }

    function startPolling() {
        stopPolling();
        pollingActive = true;
        pollFailureCount = 0;
        fetchAndRenderStatus();
    }

    function stopPolling() {
        pollingActive = false;
        if (pollTimer) {
            clearTimeout(pollTimer);
            pollTimer = null;
        }
    }

    function showLoginPanel() {
        $('#main-panel').addClass('hidden');
        $('#login-panel').removeClass('hidden');
    }

    function showMainPanel(username) {
        $('#login-panel').addClass('hidden');
        $('#main-panel').removeClass('hidden');
        $('#user-info').text('欢迎, ' + Utils.escapeHtml(username || ''));
        startPolling();
    }

    function createProcessActionHandler(apiMethod, successMsg, failMsg) {
        return function () {
            const name = $(this).data('name');
            apiMethod(name).done(function (res) {
                Utils.showToast(res.success ? successMsg : res.message, !res.success);
                fetchAndRenderStatus();
            }).fail(function (xhr) {
                Utils.showToast(Utils.getApiError(xhr, failMsg), true);
            });
        };
    }

    function initAuth() {
        API.checkLogin()
            .done(function (res) {
                if (res.success && res.data && res.data.username) {
                    showMainPanel(res.data.username);
                } else {
                    showLoginPanel();
                }
            })
            .fail(function () {
                showLoginPanel();
            });
    }

    function initLoginForm() {
        $('#login-form').on('submit', function (e) {
            e.preventDefault();
            const username = $('#username').val().trim();
            const password = $('#password').val();
            $('#login-error').text('');

            if (!username || !password) {
                $('#login-error').text('请输入用户名和密码');
                return;
            }

            API.login(username, password)
                .done(function (res) {
                    if (res.success) {
                        showMainPanel(res.data.username);
                    } else {
                        $('#login-error').text(res.message || '登录失败');
                    }
                })
                .fail(function (xhr) {
                    $('#login-error').text(Utils.getApiError(xhr, '登录失败'));
                });
        });
    }

    function initLogout() {
        $('#btn-logout').on('click', function () {
            API.logout().done(function () {
                showLoginPanel();
            });
        });
    }

    function initAddModal() {
        $('#btn-add').on('click', function () {
            $('#add-form')[0].reset();
            $('#add-error').text('');
            $('#add-status').addClass('hidden').text('');
            $('#add-submit-btn').removeClass('btn-loading').prop('disabled', false).html('添加');
            $('#add-modal .btn-cancel').prop('disabled', false);
            $('#add-modal').removeClass('hidden');
        });

        $('#add-modal .modal-close, #add-modal .btn-cancel, #add-modal .modal-overlay').on('click', function () {
            $('#add-modal').addClass('hidden');
        });

        $('#btn-query-user').on('click', function () {
            API.getCurrentUser()
                .done(function (res) {
                    if (res.success && res.data && res.data.user) {
                        $('#user').val(res.data.user);
                        Utils.showToast('已填入: ' + res.data.user);
                    } else {
                        Utils.showToast(res.message || '失败', true);
                    }
                })
                .fail(function (xhr) {
                    Utils.showToast(Utils.getApiError(xhr, '获取失败'), true);
                });
        });

        $('#add-form').on('submit', function (e) {
            e.preventDefault();
            $('#add-error').text('');
            $('#add-status').addClass('hidden').text('');

            let processName = $('#process_name').val().trim();
            processName = processName.replace(/:/g, '_').replace(/_+/g, '_').replace(/^_|_$/g, '');
            const data = {
                process_name: processName,
                command: $('#command').val().trim(),
                directory: $('#directory').val().trim(),
                user: $('#user').val().trim(),
                numprocs: parseInt($('#numprocs').val(), 10) || 1,
                autostart: $('#autostart').val(),
                autorestart: $('#autorestart').val(),
                environment: $('#environment').val().trim(),
                priority: parseInt($('#priority').val(), 10) || 999
            };

            if (!data.process_name || !data.command) {
                $('#add-error').text('名称和命令必填');
                return;
            }
            if (!/^[a-zA-Z0-9_\-]+$/.test(data.process_name)) {
                $('#add-error').text('名称仅支持字母、数字、下划线');
                return;
            }

            const $btn = $('#add-submit-btn');
            const btnOriginalHtml = $btn.html();
            $btn.addClass('btn-loading').prop('disabled', true).html('<span class="btn-spinner"></span> 添加中...');
            $('#add-modal .btn-cancel').prop('disabled', true);

            function resetAddButton() {
                $btn.removeClass('btn-loading').prop('disabled', false).html(btnOriginalHtml);
                $('#add-modal .btn-cancel').prop('disabled', false);
                $('#add-status').addClass('hidden').text('');
            }

            API.addProcess(data)
                .done(function (res) {
                    if (res.success) {
                        const addedName = (res.data && res.data.name) ? res.data.name : data.process_name;
                        $btn.html('<span class="btn-spinner"></span> 验证启动状态...');
                        $('#add-status').removeClass('hidden').text('验证中...');

                        var pollCount = 0;
                        var maxPolls = 10;
                        var pollInterval = 1500;

                        function checkProcessRunning() {
                            pollCount++;
                            API.getStatus().done(function (statusRes) {
                                if (statusRes.success && statusRes.data) {
                                    var proc = statusRes.data.find(function (p) {
                                        return (p.group || p.name) === addedName;
                                    });
                                    if (proc && (proc.statename || '').toUpperCase() === 'RUNNING') {
                                        resetAddButton();
                                        $('#add-modal').addClass('hidden');
                                        Utils.showToast('添加成功，进程已启动');
                                        fetchAndRenderStatus();
                                        return;
                                    }
                                }
                                if (pollCount < maxPolls) {
                                    setTimeout(checkProcessRunning, pollInterval);
                                } else {
                                    resetAddButton();
                                    $('#add-modal').addClass('hidden');
                                    Utils.showToast('添加成功');
                                    fetchAndRenderStatus();
                                }
                            }).fail(function () {
                                if (pollCount < maxPolls) {
                                    setTimeout(checkProcessRunning, pollInterval);
                                } else {
                                    resetAddButton();
                                    $('#add-modal').addClass('hidden');
                                    Utils.showToast('添加成功');
                                    fetchAndRenderStatus();
                                }
                            });
                        }
                        setTimeout(checkProcessRunning, pollInterval);
                    } else {
                        resetAddButton();
                        $('#add-error').text(res.message || '添加失败');
                    }
                })
                .fail(function (xhr) {
                    resetAddButton();
                    $('#add-error').text(Utils.getApiError(xhr, '添加失败'));
                });
        });
    }

    function initDeleteModal() {
        $(document).on('click', '.btn-delete', function () {
            deleteTargetName = $(this).data('name');
            $('#delete-process-name').text(Utils.escapeHtml(deleteTargetName));
            $('#delete-modal').removeClass('hidden');
        });

        $('#delete-modal .modal-close, #delete-modal .btn-cancel, #delete-modal .modal-overlay').on('click', function () {
            $('#delete-modal').addClass('hidden');
            deleteTargetName = null;
        });

        $('#btn-confirm-delete').on('click', function () {
            if (!deleteTargetName) return;

            API.deleteProcess(deleteTargetName)
                .done(function (res) {
                    $('#delete-modal').addClass('hidden');
                    deleteTargetName = null;
                    if (res.success) {
                        Utils.showToast('删除成功');
                        fetchAndRenderStatus();
                    } else {
                        Utils.showToast(res.message || '删除失败', true);
                    }
                })
                .fail(function (xhr) {
                    Utils.showToast(Utils.getApiError(xhr, '删除失败'), true);
                });
        });
    }

    function initRefreshButton() {
        $('#btn-refresh').on('click', function () {
            fetchAndRenderStatus();
            Utils.showToast('已刷新');
        });
    }

    function initPagination() {
        $(document).on('click', '.btn-page-prev', function () {
            if (currentPage > 1) {
                currentPage--;
                renderProcessTable(lastProcessList);
            }
        });
        $(document).on('click', '.btn-page-next', function () {
            const totalPages = Math.ceil(lastProcessList.length / PAGE_SIZE);
            if (currentPage < totalPages) {
                currentPage++;
                renderProcessTable(lastProcessList);
            }
        });
    }

    function showProcessMgmtPopover($trigger) {
        const name = $trigger.data('name');
        if (!name) return;
        const $pop = $('#process-mgmt-popover');
        $pop.find('.popover-btn-start').data('name', name);
        $pop.find('.popover-btn-stop').data('name', name);
        $pop.find('.popover-btn-restart').data('name', name);
        $pop.removeClass('hidden');
        const offset = $trigger.offset();
        const popW = $pop.outerWidth();
        const popH = $pop.outerHeight();
        const scrollTop = $(window).scrollTop();
        const scrollLeft = $(window).scrollLeft();
        let left = offset.left - scrollLeft + ($trigger.outerWidth() / 2) - (popW / 2);
        let top = offset.top - scrollTop - popH - 8;
        if (left < 10) left = 10;
        if (left + popW > $(window).width() - 10) left = $(window).width() - popW - 10;
        if (top < 10) top = offset.top - scrollTop + $trigger.outerHeight() + 8;
        $pop.css({ left: left + 'px', top: top + 'px' });
        setTimeout(function () {
            $(document).one('click.processMgmt', function (e) {
                if (!$pop.is(e.target) && $pop.has(e.target).length === 0 && !$trigger.is(e.target)) {
                    $pop.addClass('hidden');
                }
            });
        }, 0);
    }

    function hideProcessMgmtPopover() {
        $('#process-mgmt-popover').addClass('hidden');
        $(document).off('click.processMgmt');
    }

    function showPidPopover($trigger) {
        const pid = $trigger.data('pid');
        if (pid == null || pid === '') return;
        const pidStr = String(pid);
        const $pop = $('#pid-popover');
        $pop.find('.popover-pid-content').text(pidStr.replace(/,/g, ', '));
        $pop.removeClass('hidden');
        const offset = $trigger.offset();
        const popW = $pop.outerWidth();
        const popH = $pop.outerHeight();
        const scrollTop = $(window).scrollTop();
        const scrollLeft = $(window).scrollLeft();
        let left = offset.left - scrollLeft + ($trigger.outerWidth() / 2) - (popW / 2);
        let top = offset.top - scrollTop - popH - 8;
        if (left < 10) left = 10;
        if (left + popW > $(window).width() - 10) left = $(window).width() - popW - 10;
        if (top < 10) top = offset.top - scrollTop + $trigger.outerHeight() + 8;
        $pop.css({ left: left + 'px', top: top + 'px' });
        setTimeout(function () {
            $(document).one('click.pidPopover', function (e) {
                if (!$pop.is(e.target) && $pop.has(e.target).length === 0 && !$trigger.is(e.target)) {
                    $pop.addClass('hidden');
                }
            });
        }, 0);
    }

    function initProcessActions() {
        $(document).on('click', '.pid-trigger', function (e) {
            e.stopPropagation();
            hideProcessMgmtPopover();
            $('#pid-popover').addClass('hidden');
            $(document).off('click.pidPopover');
            showPidPopover($(this));
        });
        $(document).on('click', '.status-trigger', function (e) {
            e.stopPropagation();
            $('#pid-popover').addClass('hidden');
            $(document).off('click.pidPopover');
            hideProcessMgmtPopover();
            showProcessMgmtPopover($(this));
        });
        $(document).on('click', '.popover-btn-start', function () {
            const name = $(this).data('name');
            hideProcessMgmtPopover();
            API.startProcess(name).done(function (res) {
                Utils.showToast(res.success ? '启动成功' : res.message, !res.success);
                fetchAndRenderStatus();
            }).fail(function (xhr) {
                Utils.showToast(Utils.getApiError(xhr, '启动失败'), true);
            });
        });
        $(document).on('click', '.popover-btn-stop', function () {
            const name = $(this).data('name');
            hideProcessMgmtPopover();
            API.stopProcess(name).done(function (res) {
                Utils.showToast(res.success ? '停止成功' : res.message, !res.success);
                fetchAndRenderStatus();
            }).fail(function (xhr) {
                Utils.showToast(Utils.getApiError(xhr, '停止失败'), true);
            });
        });
        $(document).on('click', '.popover-btn-restart', function () {
            const name = $(this).data('name');
            hideProcessMgmtPopover();
            API.restartProcess(name).done(function (res) {
                Utils.showToast(res.success ? '重启成功' : res.message, !res.success);
                fetchAndRenderStatus();
            }).fail(function (xhr) {
                Utils.showToast(Utils.getApiError(xhr, '重启失败'), true);
            });
        });

        $(document).on('click', '.btn-log', function () {
            const displayName = $(this).data('name');
            const logName = $(this).data('log-name') || displayName;
            $('#log-process-name').text(Utils.escapeHtml(displayName));
            $('#process-log-modal').removeClass('hidden');
            $('#process-log-anomaly').addClass('hidden').text('');
            API.getProcessLog(logName).done(function (res) {
                const content = loadLogContent(res, '加载失败');
                $('#process-log-content').text(content);
                if (content && content.indexOf('Could not open input file') !== -1) {
                    $('#process-log-anomaly').removeClass('hidden').text('检测到异常：PHP 无法找到脚本文件，请通过「编辑」修正 command 中的路径。');
                }
            });
        });

        $(document).on('click', '.btn-config', function () {
            const name = $(this).data('name');
            $('#config-process-name').text(Utils.escapeHtml(name));
            $('#config-modal').removeClass('hidden');
            API.getProcessConfig(name).done(function (res) {
                $('#config-content').text(loadLogContent(res, '加载失败'));
            });
        });

        $(document).on('click', '.btn-edit', function () {
            const name = $(this).data('name');
            $('#edit-process-name').text(Utils.escapeHtml(name));
            $('#edit_process_name').val(name);
            $('#edit-error').text('');
            $('#edit-modal').removeClass('hidden');
            API.getProcessEditConfig(name).done(function (res) {
                if (res.success && res.data) {
                    const d = res.data;
                    $('#edit_command').val(d.command || '');
                    $('#edit_directory').val(d.directory || '');
                    $('#edit_user').val(d.user || '');
                    $('#edit_numprocs').val(d.numprocs || 1);
                    $('#edit_autostart').val(d.autostart || 'true');
                    $('#edit_autorestart').val(d.autorestart || 'unexpected');
                    $('#edit_environment').val(d.environment || '');
                    $('#edit_priority').val(d.priority || 999);
                } else {
                    $('#edit-error').text(res.message || '获取失败');
                }
            }).fail(function (xhr) {
                $('#edit-error').text(Utils.getApiError(xhr, '获取失败'));
            });
        });
    }

    function initEditModal() {
        $('#edit-modal .modal-close, #edit-modal .btn-cancel, #edit-modal .modal-overlay').on('click', function () {
            $('#edit-modal').addClass('hidden');
        });

        $('#btn-edit-query-user').on('click', function () {
            API.getCurrentUser()
                .done(function (res) {
                    if (res.success && res.data && res.data.user) {
                        $('#edit_user').val(res.data.user);
                        Utils.showToast('已填入: ' + res.data.user);
                    } else {
                        Utils.showToast(res.message || '失败', true);
                    }
                })
                .fail(function (xhr) {
                    Utils.showToast(Utils.getApiError(xhr, '获取失败'), true);
                });
        });

        $('#edit-form').on('submit', function (e) {
            e.preventDefault();
            $('#edit-error').text('');
            const name = $('#edit_process_name').val();
            const data = {
                process_name: name,
                command: $('#edit_command').val().trim(),
                directory: $('#edit_directory').val().trim(),
                user: $('#edit_user').val().trim(),
                numprocs: parseInt($('#edit_numprocs').val(), 10) || 1,
                autostart: $('#edit_autostart').val(),
                autorestart: $('#edit_autorestart').val(),
                environment: $('#edit_environment').val().trim(),
                priority: parseInt($('#edit_priority').val(), 10) || 999
            };
            if (!data.command) {
                $('#edit-error').text('命令必填');
                return;
            }
            API.updateProcess(name, data)
                .done(function (res) {
                    if (res.success) {
                        $('#edit-modal').addClass('hidden');
                        Utils.showToast('更新成功');
                        fetchAndRenderStatus();
                    } else {
                        $('#edit-error').text(res.message || '更新失败');
                    }
                })
                .fail(function (xhr) {
                    $('#edit-error').text(Utils.getApiError(xhr, '更新失败'));
                });
        });
    }

    function initSupervisorService() {
        $('#btn-svc-restart').on('click', function () {
            API.supervisorRestart().done(function (res) {
                Utils.showToast(res.success ? 'SuperVisord 重启成功' : res.message, !res.success);
                setTimeout(updateSupervisorStatus, 2000);
            }).fail(function (xhr) {
                Utils.showToast(Utils.getApiError(xhr, '重启失败'), true);
            });
        });
        $('#btn-svc-stop').on('click', function () {
            $('#stop-supervisor-modal').removeClass('hidden');
        });
        $('#btn-svc-start').on('click', function () {
            API.supervisorStart().done(function (res) {
                Utils.showToast(res.success ? 'SuperVisord 启动成功' : res.message, !res.success);
                setTimeout(updateSupervisorStatus, 2000);
            }).fail(function (xhr) {
                Utils.showToast(Utils.getApiError(xhr, '启动失败'), true);
            });
        });
    }

    function initLogsSection() {
        $('.btn-log-tab').on('click', function () {
            $('.btn-log-tab').removeClass('active');
            $(this).addClass('active');
            loadLog($(this).data('tab'));
        });
        loadLog('service');
    }

    function initModals() {
        $('#process-log-modal .modal-close, #process-log-modal .modal-overlay').on('click', function () {
            $('#process-log-modal').addClass('hidden');
        });
        $('#config-modal .modal-close, #config-modal .modal-overlay').on('click', function () {
            $('#config-modal').addClass('hidden');
        });
        $('#stop-supervisor-modal .modal-close, #stop-supervisor-modal .btn-cancel, #stop-supervisor-modal .modal-overlay').on('click', function () {
            $('#stop-supervisor-modal').addClass('hidden');
        });
        $('#btn-confirm-stop-supervisor').on('click', function () {
            $('#stop-supervisor-modal').addClass('hidden');
            API.supervisorShutdown().done(function (res) {
                Utils.showToast(res.success ? 'SuperVisord 已停止' : res.message, !res.success);
                updateSupervisorStatus();
            }).fail(function (xhr) {
                Utils.showToast(Utils.getApiError(xhr, '停止失败'), true);
            });
        });
    }

    $(function () {
        initAuth();
        initLoginForm();
        initLogout();
        initAddModal();
        initEditModal();
        initDeleteModal();
        initRefreshButton();
        initPagination();
        initProcessActions();
        initSupervisorService();
        initLogsSection();
        initModals();
    });

})(jQuery);
