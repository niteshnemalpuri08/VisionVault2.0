// frontend/auth.js  —  Unified Auth Manager
// Key: always uses 'user' to match login.html and all dashboard pages.

const authManager = {

    // ── 1. Get User ──────────────────────────────────────────
    getUser: function () {
        const raw = localStorage.getItem('user');
        if (!raw) return null;
        try { return JSON.parse(raw); }
        catch (e) { return null; }
    },

    // ── 2. Check Auth on Page Load ────────────────────────────
    checkAuth: function () {
        const user = this.getUser();
        if (!user) {
            const inDash = window.location.pathname.includes('_dash');
            window.location.href = inDash ? '../login.html' : 'login.html';
            return false;
        }
        return true;
    },

    // ── 3. Save Session ───────────────────────────────────────
    login: function (userData) {
        localStorage.setItem('user', JSON.stringify(userData));
    },

    // ── 4. Logout ─────────────────────────────────────────────
    logout: function () {
        localStorage.removeItem('user');
        const inDash = window.location.pathname.includes('_dash');
        window.location.href = inDash ? '../login.html' : 'login.html';
    },

    // ── 5. Authenticated Fetch ────────────────────────────────
    //      Wraps fetch() and attaches user context headers.
    //      Falls back gracefully if user is not logged in.
    apiCall: async function (url, options = {}) {
        const user = this.getUser();
        const headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
        if (user && user.username) {
            headers['X-Username'] = user.username;
        }
        return fetch(url, Object.assign({}, options, { headers }));
    }
};

// Export globally
window.authManager = authManager;