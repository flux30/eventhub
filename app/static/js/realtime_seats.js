/**
 * Feature 6 — Real-time Seat Count
 *
 * Strategy:
 *   1. Read Firebase config from <script id="firebaseConfig"> JSON tag
 *   2. Try Firestore onSnapshot — instant, cross-tab, zero-polling
 *   3. If no snapshot within FIREBASE_TIMEOUT_MS → silently switch to polling
 *   4. Both paths call updateSeatUI(data) — single DOM update function
 *
 * Required on the capacity container element:
 *   data-event-id="123"
 *   data-max-participants="50"
 *   data-allow-waitlist="true|false"
 */
(function () {
  'use strict';

  const FIREBASE_TIMEOUT_MS = 5000;
  const POLL_INTERVAL_MS    = 15000;

  // ── Find capacity container ──────────────────────────────────────────────────
  const container = document.querySelector('[data-event-id]');
  if (!container) return;

  const eventId        = container.dataset.eventId;
  const maxPart        = parseInt(container.dataset.maxParticipants, 10) || 1;
  const allowWaitlist  = container.dataset.allowWaitlist === 'true';

  // ── DOM refs (null-safe — organizer view may not have register buttons) ──────
  const capFill        = document.getElementById('capFill');
  const seatsText      = document.getElementById('seatsText');
  const capPct         = document.getElementById('capPct');
  const registerForm   = document.getElementById('registerForm');
  const waitlistForm   = document.getElementById('waitlistForm');
  const eventFullBtn   = document.getElementById('eventFullBtn');
  const liveIndicator  = document.getElementById('liveIndicator');

  // Status banner — may already exist in DOM (Feature 3) or be dynamically shown
  let statusBanner = document.getElementById('statusBanner');

  let firebaseConnected = false;
  let pollTimer         = null;
  let unsubscribeSnap   = null;

  // ── Boot ─────────────────────────────────────────────────────────────────────
  function init() {
    const cfg = getFirebaseConfig();
    if (cfg && cfg.projectId) {
      startFirebaseListener(cfg);
      setTimeout(function () {
        if (!firebaseConnected) {
          console.info('[Seats] Firebase timeout — switching to polling');
          setIndicator('polling');
          startPolling();
        }
      }, FIREBASE_TIMEOUT_MS);
    } else {
      console.info('[Seats] Firebase not configured — polling fallback');
      setIndicator('polling');
      startPolling();
    }
  }

  // ── Firebase Firestore onSnapshot ────────────────────────────────────────────
  function startFirebaseListener(cfg) {
    try {
      if (typeof firebase === 'undefined') {
        setIndicator('polling');
        startPolling();
        return;
      }

      let app;
      try { app = firebase.app(); }
      catch (_) { app = firebase.initializeApp(cfg); }

      const db  = firebase.firestore(app);
      const ref = db.collection('events').doc(String(eventId));

      unsubscribeSnap = ref.onSnapshot(
        function (doc) {
          if (!doc.exists) return;

          if (!firebaseConnected) {
            firebaseConnected = true;
            stopPolling();
            setIndicator('live');
            console.info('[Seats] onSnapshot live for event', eventId);
          }

          const d = doc.data();
          updateSeatUI({
            available_seats:  d.available_seats,
            max_participants: d.max_participants || maxPart,
            status:           d.status           || 'active',
            status_reason:    d.status_reason    || '',
            postponed_to:     d.postponed_to     || null,
          });
        },
        function (err) {
          console.warn('[Seats] Snapshot error:', err.message);
          if (!firebaseConnected) {
            setIndicator('polling');
            startPolling();
          }
        }
      );
    } catch (err) {
      console.warn('[Seats] Firebase init error:', err.message);
      setIndicator('polling');
      startPolling();
    }
  }

  // ── SQLite polling fallback ───────────────────────────────────────────────────
  function startPolling() {
    if (pollTimer) return;
    fetchStatus();
    pollTimer = setInterval(fetchStatus, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function fetchStatus() {
    fetch('/participant/api/event-status/' + eventId, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (data) { updateSeatUI(data); })
      .catch(function (err) {
        console.warn('[Seats] Poll failed:', err);
      });
  }

  // ── Unified DOM updater ───────────────────────────────────────────────────────
  function updateSeatUI(data) {
    const seats  = parseInt(data.available_seats, 10);
    const max    = parseInt(data.max_participants, 10) || maxPart;
    const pct    = Math.min(100, Math.max(0, Math.round(((max - seats) / max) * 100)));
    const status = data.status || 'active';

    // Capacity bar fill
    if (capFill) {
      capFill.style.width = pct + '%';
      capFill.className   = 'cap-fill ' + fillClass(pct);
    }

    // Seats available text
    if (seatsText) {
      if (seats > 0) {
        seatsText.textContent = seats + (seats === 1 ? ' seat left' : ' seats left');
        seatsText.className   = 'seats-ok';
      } else {
        seatsText.textContent = 'Event Full';
        seatsText.className   = 'seats-full';
      }
    }

    // Percentage label
    if (capPct) {
      capPct.textContent = pct + '% filled';
    }

    // Register / waitlist / full button visibility
    if (status === 'active') {
      updateRegisterButtons(seats);
    }

    // Status banner (Feature 3 integration)
    updateStatusBanner(status, data.status_reason, data.postponed_to);
  }

  function updateRegisterButtons(seats) {
    if (registerForm) {
      registerForm.style.display = seats > 0 ? '' : 'none';
    }
    if (waitlistForm) {
      waitlistForm.style.display = seats <= 0 && allowWaitlist ? '' : 'none';
    }
    if (eventFullBtn) {
      eventFullBtn.style.display = seats <= 0 && !allowWaitlist ? '' : 'none';
    }
  }

  function updateStatusBanner(status, reason, postponedTo) {
    // Create banner dynamically if it doesn't exist in the DOM yet
    if (!statusBanner && status !== 'active') {
      statusBanner = document.createElement('div');
      statusBanner.id = 'statusBanner';
      const pageContainer = document.querySelector('.page-container');
      if (pageContainer) {
        pageContainer.insertBefore(statusBanner, pageContainer.firstChild);
      }
    }
    if (!statusBanner) return;

    if (status === 'cancelled') {
      statusBanner.className    = 'status-banner cancelled';
      statusBanner.style.display = 'flex';
      statusBanner.innerHTML    =
        '<i class="fas fa-times-circle"></i>' +
        '<div><strong>This event has been cancelled.</strong>' +
        (reason ? '<span>' + esc(reason) + '</span>' : '') +
        '</div>';
    } else if (status === 'postponed') {
      statusBanner.className    = 'status-banner postponed';
      statusBanner.style.display = 'flex';
      statusBanner.innerHTML    =
        '<i class="fas fa-calendar-times"></i>' +
        '<div><strong>This event has been postponed.</strong>' +
        (postponedTo ? '<span>New date: ' + esc(postponedTo) + '</span>' : '') +
        (reason ? '<span>' + esc(reason) + '</span>' : '') +
        '</div>';
    } else {
      statusBanner.style.display = 'none';
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────────
  function fillClass(pct) {
    if (pct >= 90) return 'fill-red';
    if (pct >= 60) return 'fill-yellow';
    return 'fill-green';
  }

  function setIndicator(mode) {
    if (!liveIndicator) return;
    if (mode === 'live') {
      liveIndicator.textContent = '● Live';
      liveIndicator.className   = 'live-dot live';
      liveIndicator.title       = 'Real-time seat updates via Firebase';
    } else {
      liveIndicator.textContent = '○ Syncing';
      liveIndicator.className   = 'live-dot polling';
      liveIndicator.title       = 'Seat count refreshes every 15 seconds';
    }
  }

  function getFirebaseConfig() {
    const el = document.getElementById('firebaseConfig');
    if (!el) return null;
    try { return JSON.parse(el.textContent); }
    catch (_) { return null; }
  }

  function esc(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Cleanup
  window.addEventListener('beforeunload', function () {
    stopPolling();
    if (unsubscribeSnap) unsubscribeSnap();
  });

  init();
})();
