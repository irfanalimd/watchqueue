// WatchQueue Frontend Application

const API_BASE = '/api';
const WS_BASE = `ws://${window.location.host}`;
const REACTION_TYPES = ['fire', 'sleepy', 'laughing', 'scream', 'hundred'];
const REACTION_EMOJI = {
    fire: '🔥',
    sleepy: '😴',
    laughing: '😂',
    scream: '😱',
    hundred: '💯',
};

// State
const state = {
    currentUser: null,
    sessionToken: null,
    googleClientId: null,
    currentRoom: null,
    joinedRooms: [],
    queue: [],
    userVotes: {},
    reactions: {},
    ws: null,
    onlineUsers: [],
    selectionInProgress: false,
    selectionRequestPending: false,
    localSelectionItemId: null,
    providerFilter: '',
    availableNowOnly: false,
};

// DOM Elements
const elements = {
    // Screens
    landingScreen: document.getElementById('landing-screen'),
    roomScreen: document.getElementById('room-screen'),

    // Modals
    createModal: document.getElementById('create-modal'),
    joinModal: document.getElementById('join-modal'),

    // Forms
    createRoomForm: document.getElementById('create-room-form'),
    joinRoomForm: document.getElementById('join-room-form'),
    addMovieForm: document.getElementById('add-movie-form'),
    nameConflictModal: document.getElementById('name-conflict-modal'),
    nameConflictText: document.getElementById('name-conflict-text'),
    nameConflictKeepBtn: document.getElementById('name-conflict-keep-btn'),
    nameConflictChangeBtn: document.getElementById('name-conflict-change-btn'),
    nameConflictCloseBtn: document.getElementById('name-conflict-close'),

    // Room elements
    roomTitle: document.getElementById('room-title'),
    displayRoomCode: document.getElementById('display-room-code'),
    roomMembers: document.getElementById('room-members'),
    roleBadge: document.getElementById('role-badge'),
    shareAdminBtn: document.getElementById('share-admin-btn'),
    deleteRoomBtn: document.getElementById('delete-room-btn'),
    queueList: document.getElementById('queue-list'),
    emptyQueue: document.getElementById('empty-queue'),
    selectionMode: document.getElementById('selection-mode'),
    providerFilter: document.getElementById('provider-filter'),
    availableOnlyToggle: document.getElementById('available-only-toggle'),
    savedRoomsList: document.getElementById('saved-rooms-list'),

    // Selection overlay
    wheelOverlay: document.getElementById('wheel-overlay'),
    wheelHeader: document.getElementById('wheel-header-text'),
    wheelCanvas: document.getElementById('wheel-canvas'),
    wheelResult: document.getElementById('wheel-result'),
    confettiCanvas: document.getElementById('confetti-canvas'),
    selectedPoster: document.getElementById('selected-poster'),
    selectedTitle: document.getElementById('selected-title'),
    selectedMeta: document.getElementById('selected-meta'),
    playNowLink: document.getElementById('play-now-link'),

    // History
    historySidebar: document.getElementById('history-sidebar'),
    historyList: document.getElementById('history-list'),

    // Toast
    toastContainer: document.getElementById('toast-container'),
    activityToastContainer: document.getElementById('activity-toast-container'),
    googleSigninBtn: document.getElementById('google-signin-btn'),
    logoutBtn: document.getElementById('logout-btn'),
    authUserLabel: document.getElementById('auth-user-label'),
};

// Utility Functions
function isCurrentUserAdmin() {
    if (!state.currentRoom || !state.currentUser) return false;
    return (state.currentRoom.admins || []).includes(state.currentUser.user_id);
}

function updateAuthUI() {
    if (state.currentUser) {
        elements.logoutBtn.style.display = 'inline-flex';
        elements.authUserLabel.textContent = `Signed in as ${state.currentUser.email || state.currentUser.user_id}`;
    } else {
        elements.logoutBtn.style.display = 'none';
        elements.authUserLabel.textContent = 'Sign in with Google to create/join rooms';
    }
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    elements.toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 3000);
}

function showActivityToast(message) {
    const toast = document.createElement('div');
    toast.className = 'toast activity';
    toast.textContent = message;
    elements.activityToastContainer.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 2500);
}

function showScreen(screenId) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    document.getElementById(screenId).classList.add('active');
}

function showModal(modalId) {
    document.getElementById(modalId).classList.add('active');
}

function hideModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}

function getSelectedAvatar(pickerId) {
    const selected = document.querySelector(`#${pickerId} .avatar-option.selected`);
    return selected ? selected.dataset.avatar : '😀';
}

function askNameConflictChoice(oldName, newName) {
    return new Promise((resolve) => {
        elements.nameConflictText.textContent = `You're already in this room as "${oldName}".`;
        elements.nameConflictModal.classList.add('active');

        const cleanup = () => {
            elements.nameConflictModal.classList.remove('active');
            elements.nameConflictKeepBtn.removeEventListener('click', onKeep);
            elements.nameConflictChangeBtn.removeEventListener('click', onChange);
            elements.nameConflictCloseBtn.removeEventListener('click', onClose);
            elements.nameConflictModal.removeEventListener('click', onBackdrop);
        };

        const onKeep = () => {
            cleanup();
            resolve('keep');
        };
        const onChange = () => {
            cleanup();
            resolve('change');
        };
        const onClose = () => {
            cleanup();
            resolve('keep');
        };
        const onBackdrop = (e) => {
            if (e.target === elements.nameConflictModal) {
                cleanup();
                resolve('keep');
            }
        };

        elements.nameConflictKeepBtn.addEventListener('click', onKeep);
        elements.nameConflictChangeBtn.addEventListener('click', onChange);
        elements.nameConflictCloseBtn.addEventListener('click', onClose);
        elements.nameConflictModal.addEventListener('click', onBackdrop);
    });
}

class WheelSpinner {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.items = [];
        this.rotation = 0;
        this.colors = ['#ef4444', '#f97316', '#eab308', '#22c55e', '#06b6d4', '#3b82f6', '#ec4899', '#a855f7'];
        this.frameId = null;
    }

    setItems(queue) {
        this.items = (queue || []).map(item => ({
            _id: item._id,
            title: item.title || 'Untitled',
            poster_url: item.poster_url || null,
        }));
        this.draw();
    }

    draw() {
        const ctx = this.ctx;
        const { width, height } = this.canvas;
        const centerX = width / 2;
        const centerY = height / 2;
        const radius = Math.min(width, height) / 2 - 10;

        ctx.clearRect(0, 0, width, height);

        if (!this.items.length) {
            ctx.beginPath();
            ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
            ctx.fillStyle = '#1f2937';
            ctx.fill();
            ctx.fillStyle = '#e5e7eb';
            ctx.font = '600 16px system-ui';
            ctx.textAlign = 'center';
            ctx.fillText('Queue is empty', centerX, centerY + 6);
            return;
        }

        const segmentAngle = (Math.PI * 2) / this.items.length;
        const startOffset = -Math.PI / 2;

        this.items.forEach((item, index) => {
            const startAngle = startOffset + this.rotation + (index * segmentAngle);
            const endAngle = startAngle + segmentAngle;

            ctx.beginPath();
            ctx.moveTo(centerX, centerY);
            ctx.arc(centerX, centerY, radius, startAngle, endAngle);
            ctx.closePath();
            ctx.fillStyle = this.colors[index % this.colors.length];
            ctx.fill();

            ctx.save();
            ctx.translate(centerX, centerY);
            ctx.rotate(startAngle + (segmentAngle / 2));
            ctx.fillStyle = '#ffffff';
            ctx.font = '600 13px system-ui';
            ctx.textAlign = 'right';
            const title = item.title.length > 24 ? `${item.title.slice(0, 21)}...` : item.title;
            ctx.fillText(title, radius - 14, 4);
            ctx.restore();
        });

        ctx.beginPath();
        ctx.arc(centerX, centerY, 22, 0, Math.PI * 2);
        ctx.fillStyle = '#111827';
        ctx.fill();
        ctx.strokeStyle = '#f9fafb';
        ctx.lineWidth = 3;
        ctx.stroke();
    }

    spin(winnerIndex) {
        if (!this.items.length) return Promise.resolve();
        if (winnerIndex < 0 || winnerIndex >= this.items.length) return Promise.resolve();

        if (this.frameId) {
            cancelAnimationFrame(this.frameId);
        }

        const segmentAngle = (Math.PI * 2) / this.items.length;
        const pointerAngle = -Math.PI / 2;
        const winnerCenterAngle = (winnerIndex * segmentAngle) + (segmentAngle / 2);
        const fullTurns = (6 + Math.floor(Math.random() * 3)) * Math.PI * 2;
        const duration = 4200 + Math.random() * 900;
        const startRotation = this.rotation;
        const targetRotation = startRotation + fullTurns + (pointerAngle - winnerCenterAngle) + (Math.PI * 2);
        const startTime = performance.now();

        return new Promise(resolve => {
            const animate = (now) => {
                const elapsed = now - startTime;
                const t = Math.min(elapsed / duration, 1);
                const eased = 1 - Math.pow(1 - t, 3);

                this.rotation = startRotation + ((targetRotation - startRotation) * eased);
                this.draw();

                if (t < 1) {
                    this.frameId = requestAnimationFrame(animate);
                    return;
                }

                this.rotation = this.rotation % (Math.PI * 2);
                this.frameId = null;
                this.draw();
                resolve();
            };

            this.frameId = requestAnimationFrame(animate);
        });
    }
}

const wheelSpinner = new WheelSpinner(elements.wheelCanvas);

// API Functions
async function apiCall(endpoint, options = {}) {
    const authHeaders = state.sessionToken
        ? { 'X-Session-Token': state.sessionToken }
        : {};
    const response = await fetch(`${API_BASE}${endpoint}`, {
        headers: {
            'Content-Type': 'application/json',
            ...authHeaders,
            ...options.headers,
        },
        ...options,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'An error occurred' }));
        const detail = error?.detail;

        if (typeof detail === 'string') {
            throw new Error(detail);
        }

        if (Array.isArray(detail)) {
            const messages = detail
                .map((entry) => {
                    if (typeof entry === 'string') return entry;
                    if (entry?.msg) return entry.msg;
                    return null;
                })
                .filter(Boolean);
            throw new Error(messages.join(', ') || 'API Error');
        }

        if (detail && typeof detail === 'object') {
            if (typeof detail.msg === 'string') {
                throw new Error(detail.msg);
            }
            throw new Error(JSON.stringify(detail));
        }

        throw new Error('API Error');
    }

    if (response.status === 204) return null;
    return response.json();
}

async function fetchAuthConfig() {
    return apiCall('/auth/config');
}

async function exchangeGoogleToken(idToken) {
    return apiCall('/auth/google', {
        method: 'POST',
        body: JSON.stringify({
            id_token: idToken,
        }),
    });
}

async function getCurrentUser() {
    return apiCall('/auth/me');
}

async function logoutApi() {
    return apiCall('/auth/logout', { method: 'POST' });
}

async function createRoom(name, displayName, avatar, region = 'US') {
    return apiCall('/rooms/auth/create', {
        method: 'POST',
        body: JSON.stringify({
            name,
            display_name: displayName,
            avatar,
            region,
        }),
    });
}

async function joinRoom(code, displayName, avatar, region = 'US') {
    return apiCall(`/rooms/${code.toUpperCase()}/auth-join`, {
        method: 'POST',
        body: JSON.stringify({
            display_name: displayName,
            avatar,
            region,
        }),
    });
}

async function updateMemberProfile(roomId, member) {
    return apiCall(`/rooms/${roomId}/members/${member.user_id}`, {
        method: 'PUT',
        body: JSON.stringify(member),
    });
}

async function loadRoom(roomId) {
    return apiCall(`/rooms/${roomId}`);
}

async function loadQueue(roomId) {
    const params = new URLSearchParams();
    if (state.providerFilter) params.set('provider', state.providerFilter);
    if (state.availableNowOnly) params.set('available_now', 'true');
    const suffix = params.toString() ? `?${params.toString()}` : '';
    return apiCall(`/queue/room/${roomId}${suffix}`);
}

async function addToQueue(roomId, title) {
    return apiCall('/queue', {
        method: 'POST',
        body: JSON.stringify({
            room_id: roomId,
            title,
            added_by: state.currentUser.user_id,
        }),
    });
}

async function removeFromQueue(itemId) {
    return apiCall(`/queue/${itemId}`, { method: 'DELETE' });
}

async function castVote(itemId, voteType) {
    return apiCall('/votes', {
        method: 'POST',
        body: JSON.stringify({
            item_id: itemId,
            user_id: state.currentUser.user_id,
            vote: voteType,
        }),
    });
}

async function removeVote(itemId) {
    return apiCall(`/votes/${itemId}/${state.currentUser.user_id}`, { method: 'DELETE' });
}

async function getUserVotes(roomId) {
    return apiCall(`/votes/room/${roomId}/user/${state.currentUser.user_id}`);
}

async function selectMovie(roomId, mode) {
    return apiCall(`/queue/room/${roomId}/select?mode=${mode}`, { method: 'POST' });
}

async function toggleReaction(itemId, reaction) {
    return apiCall('/votes/reactions', {
        method: 'POST',
        body: JSON.stringify({
            item_id: itemId,
            user_id: state.currentUser.user_id,
            reaction,
        }),
    });
}

async function loadRoomReactions(roomId) {
    return apiCall(`/votes/reactions/room/${roomId}`);
}

async function listMemberRooms() {
    return apiCall('/rooms/auth/me');
}

async function leaveRoomApi(roomId, newAdminUserId = null) {
    return apiCall(`/rooms/${roomId}/leave`, {
        method: 'POST',
        body: JSON.stringify({
            user_id: state.currentUser.user_id,
            new_admin_user_id: newAdminUserId,
        }),
    });
}

async function deleteRoomApi(roomId) {
    return apiCall(`/rooms/${roomId}?acting_user_id=${encodeURIComponent(state.currentUser.user_id)}`, {
        method: 'DELETE',
    });
}

async function shareAdminApi(roomId, targetUserId) {
    return apiCall(`/rooms/${roomId}/admins`, {
        method: 'POST',
        body: JSON.stringify({
            acting_user_id: state.currentUser.user_id,
            target_user_id: targetUserId,
        }),
    });
}

async function markAsWatching(itemId) {
    return apiCall(`/queue/${itemId}/watch`, { method: 'POST' });
}

async function loadHistory(roomId) {
    return apiCall(`/votes/history/room/${roomId}`);
}

function persistAuthState() {
    if (state.sessionToken) {
        localStorage.setItem('watchqueue_session_token', state.sessionToken);
    } else {
        localStorage.removeItem('watchqueue_session_token');
    }

    localStorage.removeItem('watchqueue_user');
}

async function handleGoogleCredentialResponse(response) {
    const credential = response?.credential;
    if (!credential) {
        showToast('Google sign-in failed', 'error');
        return;
    }
    try {
        const auth = await exchangeGoogleToken(credential);
        state.sessionToken = auth.session_token;
        state.currentUser = auth.user;
        persistAuthState();
        updateAuthUI();
        await refreshMemberRooms();
        showToast('Signed in successfully', 'success');
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function initGoogleAuth() {
    try {
        const config = await fetchAuthConfig();
        state.googleClientId = config.google_client_id;
    } catch {
        state.googleClientId = null;
    }

    if (!state.googleClientId) {
        elements.googleSigninBtn.style.display = 'none';
        elements.authUserLabel.textContent = 'Google login is not configured on this server';
        return;
    }

    if (!window.google?.accounts?.id) {
        setTimeout(initGoogleAuth, 300);
        return;
    }

    window.google.accounts.id.initialize({
        client_id: state.googleClientId,
        callback: handleGoogleCredentialResponse,
    });
    window.google.accounts.id.renderButton(
        elements.googleSigninBtn,
        { theme: 'outline', size: 'large', shape: 'pill' }
    );
}

// WebSocket Functions
function connectWebSocket(roomId, userId) {
    if (state.ws) {
        state.ws.close();
    }

    const userName = encodeURIComponent(
        getMemberName(userId)
            || state.currentUser?.full_name
            || state.currentUser?.email
            || state.currentUser?.user_id
            || ''
    );
    state.ws = new WebSocket(`${WS_BASE}/ws/${roomId}/${userId}?user_name=${userName}`);

    state.ws.onopen = () => {
        console.log('WebSocket connected');
    };

    state.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data).catch((error) => {
            console.error('Failed to process websocket message:', error);
        });
    };

    state.ws.onclose = () => {
        console.log('WebSocket disconnected');
        // Attempt to reconnect after 3 seconds
        setTimeout(() => {
            if (state.currentRoom) {
                connectWebSocket(roomId, userId);
            }
        }, 3000);
    };

    state.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

async function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'presence':
            state.onlineUsers = data.users;
            updateMembersDisplay();
            break;

        case 'user_joined':
            showActivityToast(`${data.user_name || data.user_id} joined the room`);
            if (!state.onlineUsers.includes(data.user_id)) {
                state.onlineUsers.push(data.user_id);
            }
            if (state.currentRoom?._id) {
                try {
                    state.currentRoom = await loadRoom(state.currentRoom._id);
                } catch (error) {
                    console.error('Failed to refresh room on user_joined:', error);
                }
            }
            updateMembersDisplay();
            break;

        case 'user_left':
            showActivityToast(`${data.user_name || data.user_id} left the room`);
            state.onlineUsers = state.onlineUsers.filter(u => u !== data.user_id);
            if (state.currentRoom?._id) {
                try {
                    state.currentRoom = await loadRoom(state.currentRoom._id);
                } catch (error) {
                    console.error('Failed to refresh room on user_left:', error);
                }
            }
            updateMembersDisplay();
            break;

        case 'vote_update':
        case 'vote_counts':
            // Refresh queue to get updated counts
            refreshQueue();
            break;

        case 'queue_update':
            if (data.action === 'remove' && data.title) {
                showToast(`Removed "${data.title}" from queue`);
            }
            refreshQueue();
            break;

        case 'reaction_update':
            updateReactionState(data.item_id, data.reaction, data.user_id, Boolean(data.active));
            renderQueue();
            break;

        case 'selection':
            if (data.selected_by === state.currentUser?.user_id && data.item_id === state.localSelectionItemId) {
                state.localSelectionItemId = null;
                break;
            }
            playSelectionFlow({
                selectedItem: {
                    _id: data.item_id,
                    title: data.title,
                    poster_url: data.poster_url,
                },
                queueSnapshot: data.queue_snapshot || [],
                initiatedByRemote: true,
                spinnerUserId: data.selected_by,
            }).catch((error) => {
                console.error('Failed to play remote selection flow:', error);
            });
            showToast(`${data.title} was selected!`);
            break;

        case 'heartbeat':
        case 'ping':
            // Respond to ping
            if (state.ws && state.ws.readyState === WebSocket.OPEN) {
                state.ws.send(JSON.stringify({ type: 'pong' }));
            }
            break;
    }
}

function sendWebSocketMessage(type, data = {}) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ type, ...data }));
    }
}

// UI Update Functions
function updateMembersDisplay() {
    if (!state.currentRoom) return;

    elements.roomMembers.innerHTML = state.currentRoom.members
        .map(member => {
            const isOnline = state.onlineUsers.includes(member.user_id);
            const isAdmin = (state.currentRoom.admins || []).includes(member.user_id);
            return `
                <div class="member-avatar ${isOnline ? 'online' : ''}"
                     data-name="${member.name}"
                     title="${member.name}${isOnline ? ' (online)' : ''}">
                    <span class="member-main-emoji">${member.avatar}</span>
                    ${isAdmin ? '<span class="member-admin-badge">👑</span>' : ''}
                </div>
            `;
        })
        .join('');

    if (isCurrentUserAdmin()) {
        elements.roleBadge.textContent = 'Admin';
        elements.roleBadge.style.display = 'inline-flex';
        elements.shareAdminBtn.style.display = 'inline-flex';
        elements.deleteRoomBtn.style.display = 'inline-flex';
    } else {
        elements.roleBadge.textContent = '';
        elements.roleBadge.style.display = 'none';
        elements.shareAdminBtn.style.display = 'none';
        elements.deleteRoomBtn.style.display = 'none';
    }
}

function renderQueue() {
    if (state.queue.length === 0) {
        elements.emptyQueue.style.display = 'block';
        elements.queueList.querySelectorAll('.queue-item').forEach(el => el.remove());
        return;
    }

    elements.emptyQueue.style.display = 'none';

    // Keep list sorted in real-time by upvotes, then score.
    const sortedQueue = [...state.queue].sort((a, b) => {
        if ((b.upvotes || 0) !== (a.upvotes || 0)) {
            return (b.upvotes || 0) - (a.upvotes || 0);
        }
        if ((b.vote_score || 0) !== (a.vote_score || 0)) {
            return (b.vote_score || 0) - (a.vote_score || 0);
        }
        const aTime = new Date(a.added_at || 0).getTime();
        const bTime = new Date(b.added_at || 0).getTime();
        return aTime - bTime;
    });

    elements.queueList.innerHTML = sortedQueue
        .map(item => {
            const userVote = state.userVotes[item._id];
            const voteScoreClass = item.vote_score > 0 ? 'positive' : item.vote_score < 0 ? 'negative' : '';
            const reactionBarHtml = REACTION_TYPES.map((reactionType) => {
                const count = getReactionCount(item._id, reactionType);
                const active = hasUserReaction(item._id, reactionType, state.currentUser?.user_id);
                return `
                    <button class="reaction-btn ${active ? 'active' : ''}"
                            data-item="${item._id}"
                            data-reaction="${reactionType}"
                            title="${reactionType}">
                        <span class="reaction-emoji">${REACTION_EMOJI[reactionType]}</span>
                        <span class="reaction-count">${count}</span>
                    </button>
                `;
            }).join('');
            const providerBadges = (item.streaming_on || [])
                .slice(0, 4)
                .map(provider => `<span class="provider-badge">${escapeHtml(provider)}</span>`)
                .join('');
            const availability = getAvailabilityText(item);

            return `
                <div class="queue-item" data-id="${item._id}">
                    <div class="queue-item-poster">
                        ${item.poster_url
                            ? `<img src="${item.poster_url}" alt="${item.title}">`
                            : '🎬'}
                    </div>
                    <div class="queue-item-info">
                        <div class="queue-item-title">${escapeHtml(item.title)}</div>
                        <div class="queue-item-meta">
                            ${item.year ? `${item.year} · ` : ''}
                            ${item.runtime_minutes ? `${item.runtime_minutes}min · ` : ''}
                            Added by <span class="added-by">${escapeHtml(getMemberName(item.added_by))}</span>
                        </div>
                        <div class="provider-badges">${providerBadges}</div>
                        <div class="availability-count">${availability}</div>
                        <div class="reaction-bar">
                            ${reactionBarHtml}
                        </div>
                    </div>
                    <div class="queue-item-voting">
                        <button class="vote-btn upvote ${userVote === 'up' ? 'active' : ''}"
                                data-item="${item._id}" data-vote="up">
                            👍
                        </button>
                        <span class="vote-count ${voteScoreClass}">${item.vote_score}</span>
                        <button class="vote-btn downvote ${userVote === 'down' ? 'active' : ''}"
                                data-item="${item._id}" data-vote="down">
                            👎
                        </button>
                    </div>
                    <button class="queue-item-remove" data-item="${item._id}" title="Remove">
                        ✕
                    </button>
                </div>
            `;
        })
        .join('');

    // Add event listeners
    elements.queueList.querySelectorAll('.vote-btn').forEach(btn => {
        btn.addEventListener('click', handleVote);
    });

    elements.queueList.querySelectorAll('.queue-item-remove').forEach(btn => {
        btn.addEventListener('click', handleRemove);
    });

    elements.queueList.querySelectorAll('.reaction-btn').forEach(btn => {
        btn.addEventListener('click', handleReaction);
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getMemberName(userId) {
    if (state.currentRoom) {
        const member = state.currentRoom.members.find(m => m.user_id === userId);
        if (member) return member.name;
    }
    return userId;
}

function getItemTitle(itemId) {
    const item = state.queue.find(entry => entry._id === itemId);
    return item?.title || 'this item';
}

function getAvailabilityText(item) {
    if (!state.currentRoom || !item) return '';
    const members = state.currentRoom.members || [];
    if (!members.length) return 'Available to 0/0 members';

    const providersByRegion = item.providers_by_region || {};
    const availableMembers = members.filter((member) => {
        const region = (member.region || 'US').toUpperCase();
        const providers = providersByRegion[region] || [];
        return providers.length > 0;
    }).length;
    return `Available to ${availableMembers}/${members.length} members`;
}

function getReactionCount(itemId, reactionType) {
    const users = state.reactions[itemId]?.[reactionType] || [];
    return users.length;
}

function hasUserReaction(itemId, reactionType, userId) {
    const users = state.reactions[itemId]?.[reactionType] || [];
    return users.includes(userId);
}

function updateReactionState(itemId, reactionType, userId, active) {
    if (!REACTION_TYPES.includes(reactionType)) return;

    if (!state.reactions[itemId]) state.reactions[itemId] = {};
    if (!state.reactions[itemId][reactionType]) state.reactions[itemId][reactionType] = [];

    const users = state.reactions[itemId][reactionType];
    const exists = users.includes(userId);

    if (active && !exists) {
        users.push(userId);
    }
    if (!active && exists) {
        state.reactions[itemId][reactionType] = users.filter(u => u !== userId);
    }
}

async function refreshQueue() {
    try {
        const [queue, votes, reactions] = await Promise.all([
            loadQueue(state.currentRoom._id),
            getUserVotes(state.currentRoom._id),
            loadRoomReactions(state.currentRoom._id),
        ]);
        state.queue = queue;
        state.userVotes = votes;
        state.reactions = reactions || {};
        updateProviderFilterOptions(queue);
        renderQueue();
    } catch (error) {
        console.error('Failed to refresh queue:', error);
    }
}

function updateProviderFilterOptions(queue) {
    const providers = new Set();
    (queue || []).forEach(item => {
        (item.streaming_on || []).forEach(provider => providers.add(provider));
    });

    const options = ['<option value="">All providers</option>'];
    Array.from(providers).sort().forEach((provider) => {
        const selected = state.providerFilter === provider ? 'selected' : '';
        options.push(`<option value="${escapeHtml(provider)}" ${selected}>${escapeHtml(provider)}</option>`);
    });
    elements.providerFilter.innerHTML = options.join('');
}

function buildQueueSnapshot(queue) {
    return queue.map(item => ({
        _id: item._id,
        title: item.title,
        poster_url: item.poster_url || null,
    }));
}

function showWheelOverlay(queueSnapshot, title = 'Spinning the Wheel...') {
    elements.wheelHeader.textContent = title;
    elements.wheelResult.classList.remove('active');
    elements.wheelOverlay.classList.add('active');
    wheelSpinner.setItems(queueSnapshot);
}

function showSelectionResult(item) {
    if (!item) return;

    elements.selectedTitle.textContent = item.title || 'Selected';
    elements.selectedMeta.textContent = [
        item.year,
        item.runtime_minutes ? `${item.runtime_minutes} min` : null,
        item.genres?.join(', '),
    ].filter(Boolean).join(' · ') || 'No additional info';

    if (item.poster_url) {
        elements.selectedPoster.innerHTML = `<img src="${item.poster_url}" alt="${item.title}">`;
    } else {
        elements.selectedPoster.innerHTML = '🎬';
    }

    if (item.play_now_url) {
        elements.playNowLink.href = item.play_now_url;
        elements.playNowLink.style.display = 'inline-flex';
    } else {
        elements.playNowLink.removeAttribute('href');
        elements.playNowLink.style.display = 'none';
    }

    elements.wheelOverlay.dataset.itemId = item._id;
    elements.wheelResult.classList.add('active');
}

function hideWheelOverlay() {
    elements.wheelOverlay.classList.remove('active');
    elements.wheelResult.classList.remove('active');
    elements.wheelOverlay.dataset.itemId = '';
}

function canExitWheelOverlay() {
    return elements.wheelOverlay.classList.contains('active')
        && elements.wheelResult.classList.contains('active');
}

function launchConfetti() {
    const canvas = elements.confettiCanvas;
    const ctx = canvas.getContext('2d');
    const colors = ['#f59e0b', '#ef4444', '#06b6d4', '#10b981', '#8b5cf6', '#f97316'];
    const particleCount = 150;
    const gravity = 0.16;
    const drag = 0.993;
    const lifetimeMs = 3000;
    const startTime = performance.now();

    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    canvas.style.display = 'block';

    const particles = Array.from({ length: particleCount }, () => ({
        x: canvas.width / 2 + (Math.random() - 0.5) * 180,
        y: canvas.height * 0.22 + (Math.random() - 0.5) * 80,
        vx: (Math.random() - 0.5) * 9,
        vy: -3 - Math.random() * 7,
        size: 4 + Math.random() * 8,
        angle: Math.random() * Math.PI * 2,
        spin: (Math.random() - 0.5) * 0.2,
        color: colors[Math.floor(Math.random() * colors.length)],
    }));

    const animate = (now) => {
        const elapsed = now - startTime;
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        particles.forEach(p => {
            p.vx *= drag;
            p.vy = (p.vy + gravity) * drag;
            p.x += p.vx;
            p.y += p.vy;
            p.angle += p.spin;

            ctx.save();
            ctx.translate(p.x, p.y);
            ctx.rotate(p.angle);
            ctx.fillStyle = p.color;
            ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.65);
            ctx.restore();
        });

        if (elapsed < lifetimeMs) {
            requestAnimationFrame(animate);
            return;
        }

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        canvas.style.display = 'none';
    };

    requestAnimationFrame(animate);
}

async function playSelectionFlow({
    selectedItem,
    queueSnapshot,
    initiatedByRemote = false,
    preShown = false,
    spinnerUserId = null,
}) {
    if (state.selectionInProgress) return;
    state.selectionInProgress = true;

    try {
        let snapshot = Array.isArray(queueSnapshot) ? [...queueSnapshot] : [];
        if (!snapshot.length) {
            snapshot = buildQueueSnapshot(state.queue);
        }

        if (!snapshot.length) {
            throw new Error('Queue is empty');
        }

        let winnerIndex = snapshot.findIndex(item => item._id === selectedItem._id);
        if (winnerIndex === -1) {
            snapshot.push({
                _id: selectedItem._id,
                title: selectedItem.title || 'Selected',
                poster_url: selectedItem.poster_url || null,
            });
            winnerIndex = snapshot.length - 1;
        }

        const resolvedItem = state.queue.find(item => item._id === selectedItem._id) || selectedItem;
        const spinnerName = spinnerUserId ? getMemberName(spinnerUserId) : 'Someone';
        const heading = `${spinnerName} is spinning the wheel...`;

        if (!preShown) {
            showWheelOverlay(snapshot, heading);
        } else {
            elements.wheelHeader.textContent = heading;
            wheelSpinner.setItems(snapshot);
        }
        await wheelSpinner.spin(winnerIndex);
        launchConfetti();
        showSelectionResult(resolvedItem);
    } finally {
        state.selectionInProgress = false;
    }
}

async function renderHistory() {
    try {
        const history = await loadHistory(state.currentRoom._id);

        if (history.length === 0) {
            elements.historyList.innerHTML = `
                <div class="empty-state">
                    <p>No watch history yet</p>
                </div>
            `;
            return;
        }

        // We need to get item details for each history entry
        elements.historyList.innerHTML = history
            .map(entry => `
                <div class="history-item">
                    <div class="history-item-poster">🎬</div>
                    <div class="history-item-info">
                        <div class="history-item-title">Watched</div>
                        <div class="history-item-date">
                            ${new Date(entry.watched_at).toLocaleDateString()}
                        </div>
                    </div>
                </div>
            `)
            .join('');
    } catch (error) {
        console.error('Failed to load history:', error);
    }
}

// Event Handlers
async function handleVote(e) {
    const btn = e.currentTarget;
    const itemId = btn.dataset.item;
    const voteType = btn.dataset.vote;
    const currentVote = state.userVotes[itemId];
    const itemTitle = getItemTitle(itemId);

    try {
        if (currentVote === voteType) {
            // Remove vote if clicking same button
            await removeVote(itemId);
            delete state.userVotes[itemId];
            showToast(`Removed your vote on "${itemTitle}"`, 'info');
        } else {
            // Cast or change vote
            await castVote(itemId, voteType);
            state.userVotes[itemId] = voteType;
            const verb = voteType === 'up' ? 'Upvoted' : 'Downvoted';
            showToast(`${verb} "${itemTitle}"`, 'success');
        }

        // Notify others via WebSocket
        sendWebSocketMessage('vote', { item_id: itemId, vote: voteType });

        // Refresh to get updated counts
        await refreshQueue();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function handleRemove(e) {
    const itemId = e.currentTarget.dataset.item;
    const itemTitle = getItemTitle(itemId);

    try {
        await removeFromQueue(itemId);
        delete state.reactions[itemId];
        sendWebSocketMessage('queue_add', { item_id: itemId, action: 'remove', title: itemTitle });
        await refreshQueue();
        showToast(`Removed "${itemTitle}" from queue`);
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function handleReaction(e) {
    const btn = e.currentTarget;
    const itemId = btn.dataset.item;
    const reactionType = btn.dataset.reaction;

    try {
        const result = await toggleReaction(itemId, reactionType);
        updateReactionState(itemId, reactionType, state.currentUser.user_id, Boolean(result.active));
        renderQueue();

        sendWebSocketMessage('reaction', {
            item_id: itemId,
            reaction: reactionType,
            active: Boolean(result.active),
        });
    } catch (error) {
        showToast(error.message, 'error');
    }
}

function persistJoinedRooms() {
    localStorage.setItem('watchqueue_joined_rooms', JSON.stringify(state.joinedRooms));
}

function upsertJoinedRoom(room) {
    if (!room?._id) return;
    const idx = state.joinedRooms.findIndex(r => r._id === room._id);
    const summary = {
        _id: room._id,
        name: room.name,
        code: room.code,
        admins: room.admins || [],
        members: room.members || [],
    };
    if (idx >= 0) {
        state.joinedRooms[idx] = summary;
    } else {
        state.joinedRooms.unshift(summary);
    }
    persistJoinedRooms();
}

function removeJoinedRoom(roomId) {
    state.joinedRooms = state.joinedRooms.filter(r => r._id !== roomId);
    persistJoinedRooms();
}

function renderSavedRooms() {
    if (!state.joinedRooms.length) {
        elements.savedRoomsList.innerHTML = '<p class="subtle">No saved rooms yet</p>';
        return;
    }

    elements.savedRoomsList.innerHTML = state.joinedRooms.map((room) => `
        <div class="saved-room-item" data-room-id="${room._id}">
            <span class="saved-room-name">${escapeHtml(room.name)}</span>
            <span class="saved-room-code">${escapeHtml(room.code)}</span>
            <span class="saved-room-members">${(room.members || []).length} members</span>
            <div class="saved-room-actions">
                <button class="btn btn-ghost saved-room-open" data-room-id="${room._id}">Open</button>
                <button class="btn btn-ghost saved-room-leave" data-room-id="${room._id}">Leave Room</button>
                ${(room.admins || []).includes(state.currentUser?.user_id)
                    ? `<button class="btn btn-danger saved-room-delete" data-room-id="${room._id}">Delete</button>`
                    : ''}
            </div>
        </div>
    `).join('');

    elements.savedRoomsList.querySelectorAll('.saved-room-open').forEach((btn) => {
        btn.addEventListener('click', async () => {
            try {
                const room = await loadRoom(btn.dataset.roomId);
                await enterRoom(room);
            } catch (error) {
                removeJoinedRoom(btn.dataset.roomId);
                renderSavedRooms();
                showToast('Room no longer exists', 'error');
            }
        });
    });

    elements.savedRoomsList.querySelectorAll('.saved-room-leave').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const roomId = btn.dataset.roomId;
            let room = state.joinedRooms.find(r => r._id === roomId);
            try {
                room = await loadRoom(roomId);
            } catch {
                removeJoinedRoom(roomId);
                renderSavedRooms();
                return;
            }

            let newAdminUserId = null;
            const isAdmin = (room.admins || []).includes(state.currentUser.user_id);
            if (isAdmin && (room.admins || []).length <= 1) {
                const candidates = (room.members || []).filter(
                    (member) => member.user_id !== state.currentUser.user_id
                );
                if (!candidates.length) {
                    showToast('You are the last member. Delete room instead.', 'error');
                    return;
                }
                const options = candidates.map((m) => `${m.user_id} (${m.name})`).join('\n');
                const selectedUserId = prompt(`Select a member to transfer admin before leaving:\n${options}`);
                if (!selectedUserId) {
                    showToast('Admin transfer is required to leave', 'error');
                    return;
                }
                newAdminUserId = selectedUserId.trim();
            }

            try {
                await leaveRoomApi(roomId, newAdminUserId);
                if (state.currentRoom?._id === roomId && state.ws) {
                    state.ws.close();
                    state.currentRoom = null;
                    state.queue = [];
                    state.userVotes = {};
                    state.reactions = {};
                    localStorage.removeItem('watchqueue_room');
                    showScreen('landing-screen');
                }
                removeJoinedRoom(roomId);
                await refreshMemberRooms();
            } catch (error) {
                showToast(error.message, 'error');
            }
        });
    });

    elements.savedRoomsList.querySelectorAll('.saved-room-delete').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const roomId = btn.dataset.roomId;
            const confirmed = confirm('Delete this room permanently?');
            if (!confirmed) return;

            try {
                await deleteRoomApi(roomId);
                if (state.currentRoom?._id === roomId && state.ws) {
                    state.ws.close();
                    state.currentRoom = null;
                    state.queue = [];
                    state.userVotes = {};
                    state.reactions = {};
                    localStorage.removeItem('watchqueue_room');
                    showScreen('landing-screen');
                }
                removeJoinedRoom(roomId);
                await refreshMemberRooms();
                showToast('Room deleted');
            } catch (error) {
                showToast(error.message, 'error');
            }
        });
    });
}

async function refreshMemberRooms() {
    if (!state.currentUser?.user_id) return;
    try {
        const rooms = await listMemberRooms();
        state.joinedRooms = rooms.map((room) => ({
            _id: room._id,
            name: room.name,
            code: room.code,
            admins: room.admins || [],
            members: room.members || [],
        }));
        persistJoinedRooms();
    } catch (error) {
        console.error('Failed to refresh room memberships:', error);
    }
    renderSavedRooms();
}

// Enter Room
async function enterRoom(room) {
    state.currentRoom = room;

    elements.roomTitle.textContent = room.name;
    elements.displayRoomCode.textContent = room.code;

    showScreen('room-screen');

    // Connect WebSocket
    connectWebSocket(room._id, state.currentUser.user_id);

    // Load queue
    await refreshQueue();

    // Update members
    updateMembersDisplay();

    // Save room to localStorage
    localStorage.setItem('watchqueue_room', room._id);
    upsertJoinedRoom(room);
    await refreshMemberRooms();
    renderSavedRooms();
}

// Initialize
function init() {
    // Avatar picker event listeners
    document.querySelectorAll('.avatar-picker').forEach(picker => {
        picker.addEventListener('click', (e) => {
            if (e.target.classList.contains('avatar-option')) {
                picker.querySelectorAll('.avatar-option').forEach(opt => opt.classList.remove('selected'));
                e.target.classList.add('selected');
            }
        });
    });

    // Landing actions
    document.getElementById('create-room-card').addEventListener('click', () => showModal('create-modal'));
    document.getElementById('join-room-card').addEventListener('click', () => showModal('join-modal'));

    // Modal close buttons
    document.querySelectorAll('.modal-close').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.closest('.modal').classList.remove('active');
        });
    });

    // Close modal on backdrop click
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
            }
        });
    });

    // Create room form
    elements.createRoomForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!state.currentUser || !state.sessionToken) {
            showToast('Please sign in with Google first', 'error');
            return;
        }
        const roomName = document.getElementById('room-name').value;
        const displayName = document.getElementById('your-name').value;
        const avatar = getSelectedAvatar('avatar-picker-create');

        try {
            const room = await createRoom(roomName, displayName, avatar, 'US');
            hideModal('create-modal');
            await enterRoom(room);
            showToast('Room created! Share the code with friends.');
        } catch (error) {
            showToast(error.message, 'error');
        }
    });

    // Join room form
    elements.joinRoomForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!state.currentUser || !state.sessionToken) {
            showToast('Please sign in with Google first', 'error');
            return;
        }
        const code = document.getElementById('room-code').value;
        const displayName = document.getElementById('join-name').value.trim();
        const avatar = getSelectedAvatar('avatar-picker-join');

        try {
            let shouldUpdateName = false;
            let effectiveName = displayName;
            let existingRoom = null;
            try {
                existingRoom = await apiCall(`/rooms/code/${code.toUpperCase()}`);
            } catch {
                existingRoom = null;
            }

            const existingMember = existingRoom?.members?.find(
                (member) => member.user_id === state.currentUser.user_id
            );
            if (existingMember && existingMember.name !== displayName) {
                const choice = await askNameConflictChoice(existingMember.name, displayName);
                if (choice === 'change') {
                    shouldUpdateName = true;
                } else {
                    effectiveName = existingMember.name;
                    document.getElementById('join-name').value = existingMember.name;
                    showToast(`Joining as "${existingMember.name}"`, 'info');
                }
            }

            let room = await joinRoom(code, effectiveName, avatar, 'US');
            if (shouldUpdateName) {
                room = await updateMemberProfile(room._id, {
                    user_id: state.currentUser.user_id,
                    name: displayName,
                    avatar,
                    region: 'US',
                });
                showToast(`Updated room name to "${displayName}"`, 'success');
            }
            hideModal('join-modal');
            await enterRoom(room);
            showToast('Joined room!');
        } catch (error) {
            showToast(error.message, 'error');
        }
    });

    // Add movie form
    elements.addMovieForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const titleInput = document.getElementById('movie-title');
        const title = titleInput.value.trim();

        if (!title) return;

        try {
            await addToQueue(state.currentRoom._id, title);
            sendWebSocketMessage('queue_add', { title });
            titleInput.value = '';
            await refreshQueue();
            showToast('Added to queue!');
        } catch (error) {
            showToast(error.message, 'error');
        }
    });

    // Pick movie button
    document.getElementById('pick-movie-btn').addEventListener('click', async () => {
        if (state.selectionInProgress || state.selectionRequestPending) {
            return;
        }

        const mode = elements.selectionMode.value;
        const queueSnapshot = buildQueueSnapshot(state.queue);

        try {
            if (!queueSnapshot.length) {
                showToast('Add at least one movie first', 'error');
                return;
            }

            state.selectionRequestPending = true;
            showWheelOverlay(queueSnapshot, 'Choosing tonight\'s pick...');
            const selected = await selectMovie(state.currentRoom._id, mode);
            state.localSelectionItemId = selected._id;
            sendWebSocketMessage('selection', {
                item_id: selected._id,
                title: selected.title,
                poster_url: selected.poster_url || null,
                queue_snapshot: queueSnapshot,
            });

            await playSelectionFlow({
                selectedItem: selected,
                queueSnapshot,
                initiatedByRemote: false,
                preShown: true,
                spinnerUserId: state.currentUser.user_id,
            });
        } catch (error) {
            hideWheelOverlay();
            showToast(error.message, 'error');
        } finally {
            state.selectionRequestPending = false;
        }
    });

    // Start watching button
    document.getElementById('start-watching-btn').addEventListener('click', async () => {
        const itemId = elements.wheelOverlay.dataset.itemId;

        try {
            await markAsWatching(itemId);
            hideWheelOverlay();
            await refreshQueue();
            showToast('Enjoy your movie! 🍿');
        } catch (error) {
            showToast(error.message, 'error');
        }
    });

    // Close selection overlay
    document.getElementById('close-selection-btn').addEventListener('click', hideWheelOverlay);

    // Allow closing the wheel result with Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && canExitWheelOverlay()) {
            hideWheelOverlay();
        }
    });

    // Copy room code
    document.getElementById('copy-code-btn').addEventListener('click', () => {
        navigator.clipboard.writeText(state.currentRoom.code);
        showToast('Code copied!');
    });

    elements.logoutBtn.addEventListener('click', async () => {
        try {
            await logoutApi();
        } catch {
            // no-op, local clear still required
        }
        if (state.ws) state.ws.close();
        state.currentUser = null;
        state.sessionToken = null;
        state.currentRoom = null;
        state.queue = [];
        state.userVotes = {};
        state.reactions = {};
        state.joinedRooms = [];
        localStorage.removeItem('watchqueue_room');
        localStorage.removeItem('watchqueue_joined_rooms');
        persistAuthState();
        renderSavedRooms();
        updateAuthUI();
        showScreen('landing-screen');
    });

    elements.providerFilter.addEventListener('change', async (e) => {
        state.providerFilter = e.target.value;
        await refreshQueue();
    });

    elements.availableOnlyToggle.addEventListener('change', async (e) => {
        state.availableNowOnly = Boolean(e.target.checked);
        await refreshQueue();
    });

    elements.shareAdminBtn.addEventListener('click', async () => {
        if (!isCurrentUserAdmin()) return;
        const candidates = (state.currentRoom.members || [])
            .filter(m => m.user_id !== state.currentUser.user_id)
            .filter(m => !(state.currentRoom.admins || []).includes(m.user_id));
        if (!candidates.length) {
            showToast('No eligible members to promote', 'info');
            return;
        }

        const options = candidates.map((m) => `${m.user_id} (${m.name})`).join('\n');
        const selectedUserId = prompt(`Enter user_id to make admin:\n${options}`);
        if (!selectedUserId) return;

        try {
            state.currentRoom = await shareAdminApi(state.currentRoom._id, selectedUserId.trim());
            updateMembersDisplay();
            showToast('Admin privileges shared');
        } catch (error) {
            showToast(error.message, 'error');
        }
    });

    elements.deleteRoomBtn.addEventListener('click', async () => {
        if (!isCurrentUserAdmin()) {
            showToast('Only admins can delete rooms', 'error');
            return;
        }

        const confirmed = confirm('Delete this room and all queue/history data permanently?');
        if (!confirmed) return;

        try {
            const roomId = state.currentRoom._id;
            await deleteRoomApi(roomId);
            if (state.ws) state.ws.close();
            state.currentRoom = null;
            state.queue = [];
            state.userVotes = {};
            state.reactions = {};
            localStorage.removeItem('watchqueue_room');
            removeJoinedRoom(roomId);
            renderSavedRooms();
            showScreen('landing-screen');
            showToast('Room deleted');
        } catch (error) {
            showToast(error.message, 'error');
        }
    });

    // Leave room
    document.getElementById('leave-room-btn').addEventListener('click', async () => {
        // "Home" behavior: keep membership, keep saved room, just exit active room view.
        if (state.ws) state.ws.close();
        state.currentRoom = null;
        state.queue = [];
        state.userVotes = {};
        state.reactions = {};
        localStorage.removeItem('watchqueue_room');
        await refreshMemberRooms();
        showScreen('landing-screen');
    });

    // History toggle
    document.getElementById('history-toggle-btn').addEventListener('click', () => {
        elements.historySidebar.classList.add('active');
        renderHistory();
    });

    document.getElementById('close-history-btn').addEventListener('click', () => {
        elements.historySidebar.classList.remove('active');
    });

    // Check for saved session
    const savedToken = localStorage.getItem('watchqueue_session_token');
    const savedRoomId = localStorage.getItem('watchqueue_room');
    const savedRooms = localStorage.getItem('watchqueue_joined_rooms');

    if (savedRooms) {
        try {
            state.joinedRooms = JSON.parse(savedRooms);
        } catch {
            state.joinedRooms = [];
        }
    }
    renderSavedRooms();

    initGoogleAuth();

    if (savedToken) {
        state.sessionToken = savedToken;
        getCurrentUser()
            .then(async (user) => {
                state.currentUser = user;
                persistAuthState();
                updateAuthUI();
                document.getElementById('your-name').value = user.full_name || '';
                document.getElementById('join-name').value = user.full_name || '';
                await refreshMemberRooms();
                if (savedRoomId) {
                    try {
                        const room = await loadRoom(savedRoomId);
                        await enterRoom(room);
                    } catch {
                        localStorage.removeItem('watchqueue_room');
                        showScreen('landing-screen');
                    }
                } else {
                    showScreen('landing-screen');
                }
            })
            .catch(() => {
                state.sessionToken = null;
                state.currentUser = null;
                persistAuthState();
                updateAuthUI();
                showScreen('landing-screen');
            });
    } else {
        updateAuthUI();
        showScreen('landing-screen');
    }
}

// Start the app
document.addEventListener('DOMContentLoaded', init);
