(function (global) {
    'use strict';

    function escapeHtml(text) {
        if (text == null) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function escapeAttr(text) {
        if (text == null) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function showToast(message, isError) {
        const $ = global.jQuery;
        if (!$) return;
        const $msg = $('<div class="toast ' + (isError ? 'toast-error' : 'toast-success') + '">' + escapeHtml(message) + '</div>');
        $('body').append($msg);
        setTimeout(function () {
            $msg.addClass('show');
        }, 10);
        setTimeout(function () {
            $msg.removeClass('show');
            setTimeout(function () { $msg.remove(); }, 300);
        }, 2500);
    }

    function getApiMessage(res, fallback) {
        if (res && res.success && res.data !== undefined) return res.data;
        return (res && res.message) || fallback || '操作失败';
    }

    function getApiError(xhr, fallback) {
        const res = xhr && xhr.responseJSON;
        return (res && res.message) || fallback || '请求失败，请重试';
    }

    global.SuperMonitorUtils = {
        escapeHtml: escapeHtml,
        escapeAttr: escapeAttr,
        showToast: showToast,
        getApiMessage: getApiMessage,
        getApiError: getApiError
    };
})(typeof window !== 'undefined' ? window : this);
