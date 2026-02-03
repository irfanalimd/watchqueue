// WatchQueue Frontend Application

const API_BASE = '/api';
const WS_BASE = `ws://${window.location.host}`;

// State
const state = {
    currentUser: null,
    currentRoom: null,
    queue: [],
    userVotes: {},
    ws: null,
    onlineUsers: [],
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

    // Room elements
    roomTitle: document.getElementById('room-title'),
    displayRoomCode: document.getElementById('display-room-code'),
    roomMembers: document.getElementById('room-members'),
    queueList: document.getElementById('queue-list'),
    emptyQueue: document.getElementById('empty-queue'),
    selectionMode: document.getElementById('selection-mode'),

    // Selection overlay
    selectionOverlay: document.getElementById('selection-overlay'),
    selectedPoster: document.getElementById('selected-poster'),
    selectedTitle: document.getElementById('selected-title'),
    selectedMeta: document.getElementById('selected-meta'),

    // History
    historySidebar: document.getElementById('history-sidebar'),
    historyList: document.getElementById('history-list'),

    // Toast
    toastContainer: document.getElementById('toast-container'),
};

// Utility Functions
function generateUserId() {
    return 'user_' + Math.random().toString(36).substr(2, 9);
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

// API Functions
async function apiCall(endpoint, options = {}) {
    const response = await fetch(`${API_BASE}${endpoint}`, {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
        ...options,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'An error occurred' }));
        throw new Error(error.detail || 'API Error');
    }

    if (response.status === 204) return null;
    return response.json();
}

async function createRoom(name, userName, avatar) {
    const userId = generateUserId();
    const room = await apiCall('/rooms', {
        method: 'POST',
        body: JSON.stringify({
            name,
            members: [{ user_id: userId, name: userName, avatar }],
        }),
    });

    state.currentUser = { user_id: userId, name: userName, avatar };
    localStorage.setItem('watchqueue_user', JSON.stringify(state.currentUser));

    return room;
}

async function joinRoom(code, userName, avatar) {
    const userId = generateUserId();
    const room = await apiCall(`/rooms/${code.toUpperCase()}/join`, {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, name: userName, avatar }),
    });

    state.currentUser = { user_id: userId, name: userName, avatar };
    localStorage.setItem('watchqueue_user', JSON.stringify(state.currentUser));

    return room;
}

async function loadRoom(roomId) {
    return apiCall(`/rooms/${roomId}`);
}

async function loadQueue(roomId) {
    return apiCall(`/queue/room/${roomId}`);
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

async function markAsWatching(itemId) {
    return apiCall(`/queue/${itemId}/watch`, { method: 'POST' });
}

async function loadHistory(roomId) {
    return apiCall(`/votes/history/room/${roomId}`);
}

// WebSocket Functions
function connectWebSocket(roomId, userId) {
    if (state.ws) {
        state.ws.close();
    }

    state.ws = new WebSocket(`${WS_BASE}/ws/${roomId}/${userId}`);

    state.ws.onopen = () => {
        console.log('WebSocket connected');
    };

    state.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
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

function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'presence':
            state.onlineUsers = data.users;
            updateMembersDisplay();
            break;

        case 'user_joined':
            showToast(`${data.user_id} joined the room`);
            if (!state.onlineUsers.includes(data.user_id)) {
                state.onlineUsers.push(data.user_id);
            }
            updateMembersDisplay();
            break;

        case 'user_left':
            showToast(`${data.user_id} left the room`);
            state.onlineUsers = state.onlineUsers.filter(u => u !== data.user_id);
            updateMembersDisplay();
            break;

        case 'vote_update':
        case 'vote_counts':
            // Refresh queue to get updated counts
            refreshQueue();
            break;

        case 'queue_update':
            refreshQueue();
            break;

        case 'selection':
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
            return `
                <div class="member-avatar ${isOnline ? 'online' : ''}"
                     data-name="${member.name}"
                     title="${member.name}${isOnline ? ' (online)' : ''}">
                    ${member.avatar}
                </div>
            `;
        })
        .join('');
}

function renderQueue() {
    if (state.queue.length === 0) {
        elements.emptyQueue.style.display = 'block';
        elements.queueList.querySelectorAll('.queue-item').forEach(el => el.remove());
        return;
    }

    elements.emptyQueue.style.display = 'none';

    // Sort by vote score
    const sortedQueue = [...state.queue].sort((a, b) => b.vote_score - a.vote_score);

    elements.queueList.innerHTML = sortedQueue
        .map(item => {
            const userVote = state.userVotes[item._id];
            const voteScoreClass = item.vote_score > 0 ? 'positive' : item.vote_score < 0 ? 'negative' : '';

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

async function refreshQueue() {
    try {
        state.queue = await loadQueue(state.currentRoom._id);
        state.userVotes = await getUserVotes(state.currentRoom._id);
        renderQueue();
    } catch (error) {
        console.error('Failed to refresh queue:', error);
    }
}

function showSelectionOverlay(item) {
    elements.selectedTitle.textContent = item.title;
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

    elements.selectionOverlay.dataset.itemId = item._id;
    elements.selectionOverlay.classList.add('active');
}

function hideSelectionOverlay() {
    elements.selectionOverlay.classList.remove('active');
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

    try {
        if (currentVote === voteType) {
            // Remove vote if clicking same button
            await removeVote(itemId);
            delete state.userVotes[itemId];
        } else {
            // Cast or change vote
            await castVote(itemId, voteType);
            state.userVotes[itemId] = voteType;
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

    try {
        await removeFromQueue(itemId);
        sendWebSocketMessage('queue_add', { item_id: itemId, action: 'remove' });
        await refreshQueue();
        showToast('Removed from queue');
    } catch (error) {
        showToast(error.message, 'error');
    }
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
        const roomName = document.getElementById('room-name').value;
        const userName = document.getElementById('your-name').value;
        const avatar = getSelectedAvatar('avatar-picker-create');

        try {
            const room = await createRoom(roomName, userName, avatar);
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
        const code = document.getElementById('room-code').value;
        const userName = document.getElementById('join-name').value;
        const avatar = getSelectedAvatar('avatar-picker-join');

        try {
            const room = await joinRoom(code, userName, avatar);
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
        const mode = elements.selectionMode.value;

        try {
            const selected = await selectMovie(state.currentRoom._id, mode);
            sendWebSocketMessage('selection', { item_id: selected._id, title: selected.title });
            showSelectionOverlay(selected);
        } catch (error) {
            showToast(error.message, 'error');
        }
    });

    // Start watching button
    document.getElementById('start-watching-btn').addEventListener('click', async () => {
        const itemId = elements.selectionOverlay.dataset.itemId;

        try {
            await markAsWatching(itemId);
            hideSelectionOverlay();
            await refreshQueue();
            showToast('Enjoy your movie! 🍿');
        } catch (error) {
            showToast(error.message, 'error');
        }
    });

    // Close selection overlay
    document.getElementById('close-selection-btn').addEventListener('click', hideSelectionOverlay);

    // Copy room code
    document.getElementById('copy-code-btn').addEventListener('click', () => {
        navigator.clipboard.writeText(state.currentRoom.code);
        showToast('Code copied!');
    });

    // Leave room
    document.getElementById('leave-room-btn').addEventListener('click', () => {
        if (state.ws) {
            state.ws.close();
        }
        state.currentRoom = null;
        state.queue = [];
        state.userVotes = {};
        localStorage.removeItem('watchqueue_room');
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
    const savedUser = localStorage.getItem('watchqueue_user');
    const savedRoomId = localStorage.getItem('watchqueue_room');

    if (savedUser && savedRoomId) {
        state.currentUser = JSON.parse(savedUser);
        loadRoom(savedRoomId)
            .then(room => {
                enterRoom(room);
            })
            .catch(() => {
                localStorage.removeItem('watchqueue_room');
                showScreen('landing-screen');
            });
    } else {
        showScreen('landing-screen');
    }
}

// Start the app
document.addEventListener('DOMContentLoaded', init);
