(function (global) {
    'use strict';

    const $ = global.jQuery;
    if (!$) return;

    const BASE = '';
    const XHR_OPTIONS = { xhrFields: { withCredentials: true } };

    function request(method, path, data) {
        const opts = Object.assign({ url: BASE + path, method: method }, XHR_OPTIONS);
        if (data !== undefined) {
            opts.contentType = 'application/json';
            opts.data = JSON.stringify(data);
        }
        return $.ajax(opts);
    }

    function get(path) {
        return request('GET', path);
    }

    function post(path, data) {
        return request('POST', path, data);
    }

    function del(path) {
        return request('DELETE', path);
    }

    function encodePath(name) {
        return encodeURIComponent(name);
    }

    const API = {
        getStatus: function () { return get('/api/status'); },
        login: function (username, password) { return post('/api/login', { username: username, password: password }); },
        checkLogin: function () { return get('/api/login'); },
        logout: function () { return post('/api/logout'); },
        addProcess: function (data) { return post('/api/process', data); },
        updateProcess: function (name, data) { return request('PUT', '/api/process/' + encodePath(name), data); },
        deleteProcess: function (name) { return del('/api/process/' + encodePath(name)); },
        startProcess: function (name) { return post('/api/process/' + encodePath(name) + '/start'); },
        stopProcess: function (name) { return post('/api/process/' + encodePath(name) + '/stop'); },
        restartProcess: function (name) { return post('/api/process/' + encodePath(name) + '/restart'); },
        getCurrentUser: function () { return get('/api/current-user'); },
        getSupervisorState: function () { return get('/api/supervisor/state'); },
        supervisorRestart: function () { return post('/api/supervisor/restart'); },
        supervisorShutdown: function () { return post('/api/supervisor/shutdown'); },
        supervisorStart: function () { return post('/api/supervisor/start'); },
        getMainLog: function () { return get('/api/logs/main'); },
        getProcessLog: function (name, type) {
            return get('/api/logs/process/' + encodePath(name) + '?type=' + (type || 'stdout'));
        },
        getProcessConfig: function (name) { return get('/api/process/' + encodePath(name) + '/config'); },
        getProcessEditConfig: function (name) { return get('/api/process/' + encodePath(name) + '/edit-config'); }
    };

    global.SuperMonitorAPI = API;
})(typeof window !== 'undefined' ? window : this);
