const API = 'http://localhost:8000';
    let SUPABASE_URL = '';
    let SUPABASE_ANON_KEY = '';

    let sb = null;
    let session = null;
    let calendarConnected = false;
    let calendarEvents = [];
    let calendarBusy = [];
    let suggestionsCache = [];
    let viewMode = 'week';
    let viewAnchor = new Date();

    const CAL_START_HOUR = 6;
    const CAL_END_HOUR = 22;
    const HOUR_HEIGHT = 48;

    function getToken() {
      return session?.access_token || '';
    }

    async function api(path, opts = {}) {
      const url = `${API}${path}`;
      const headers = { ...opts.headers, 'Content-Type': 'application/json' };
      if (getToken()) headers['Authorization'] = `Bearer ${getToken()}`;
      const res = await fetch(url, { ...opts, headers });
      if (!res.ok) {
        const text = await res.text();
        const err = new Error(text || res.statusText);
        err.status = res.status;
        throw err;
      }
      return opts.raw ? res : res.json();
    }

    function setupProfileForm() {
      const form = document.getElementById('profile-form');
      if (!form) return;
      form.onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const prefsText = fd.get('profile_preferences')?.toString().trim() || '';
        let prefs = null;
        if (prefsText) {
          try {
            prefs = JSON.parse(prefsText);
          } catch (err) {
            alert('Preferences must be valid JSON or left blank.');
            return;
          }
        }
        const status = document.getElementById('profile-status');
        status.textContent = 'Saving...';
        await api('/api/profile', {
          method: 'PUT',
          body: JSON.stringify({
            display_name: fd.get('display_name') || '',
            timezone: fd.get('timezone') || '',
            preferences: prefs || {},
          }),
        });
        status.textContent = 'Saved';
        setTimeout(() => { status.textContent = ''; }, 1500);
      };
    }

    function renderAuth() {
      const el = document.getElementById('auth-area');
      if (session) {
        el.innerHTML = `
          <div class="relative">
            <button id="user-menu-button" class="pill bg-white/10 px-3 py-2 text-sm text-white flex items-center gap-2 hover:bg-white/20">
              <span class="pill bg-[var(--accent)] text-white px-2 py-1 text-xs">${session.user?.email?.[0] || 'U'}</span>
              <span class="hidden sm:inline">${session.user?.email || ''}</span>
              <span class="text-white/70">▾</span>
            </button>
            <div id="user-menu" class="hidden absolute right-0 mt-3 w-80 card p-4 z-50">
              <div class="mb-3">
                <p class="text-xs text-[var(--muted)]">Signed in as</p>
                <p class="text-sm font-medium text-[var(--text)]">${session.user?.email || ''}</p>
              </div>
              <form id="profile-form" class="space-y-3">
                <div>
                  <label class="block text-sm text-[var(--muted)] mb-1">Display name</label>
                  <input type="text" name="display_name" placeholder="Your name"
                    class="w-full px-3 py-2 bg-white border border-[var(--panel-border)] rounded-lg text-[var(--text)] placeholder-[var(--muted)]" />
                </div>
                <div>
                  <label class="block text-sm text-[var(--muted)] mb-1">Timezone</label>
                  <input type="text" name="timezone" placeholder="Timezone from Google Calendar"
                    class="w-full px-3 py-2 bg-white border border-[var(--panel-border)] rounded-lg text-[var(--text)] placeholder-[var(--muted)]" />
                </div>
                <div>
                  <label class="block text-sm text-[var(--muted)] mb-1">Preferences (JSON)</label>
                  <textarea name="profile_preferences" rows="3" placeholder='{"focus":"deep","avoid":["Fridays"]}'
                    class="w-full px-3 py-2 bg-white border border-[var(--panel-border)] rounded-lg text-[var(--text)] placeholder-[var(--muted)]"></textarea>
                </div>
                <div class="flex items-center gap-3">
                  <button type="submit" class="px-4 py-2 btn-accent pill text-sm font-medium">
                    Save profile
                  </button>
                  <span id="profile-status" class="text-sm text-[var(--muted)]"></span>
                </div>
              </form>
              <div class="mt-4 flex justify-between items-center">
                <span class="text-xs text-[var(--muted)]">Profile & settings</span>
                <button id="btn-signout" class="text-[var(--accent-strong)] text-sm font-semibold">Sign out</button>
              </div>
            </div>
          </div>`;
        const menuBtn = document.getElementById('user-menu-button');
        const menu = document.getElementById('user-menu');
        const toggleMenu = (e) => {
          e.stopPropagation();
          menu.classList.toggle('hidden');
        };
        menuBtn.onclick = toggleMenu;
        document.addEventListener('click', (e) => {
          if (!menu.contains(e.target) && !menuBtn.contains(e.target)) {
            menu.classList.add('hidden');
          }
        });
        document.getElementById('btn-signout').onclick = () => { sb.auth.signOut(); };
        setupProfileForm();
      } else {
        el.innerHTML = '';
      }
    }

    function showMain() {
      document.getElementById('login-screen').classList.add('hidden');
      document.getElementById('main-screen').classList.remove('hidden');
    }

    function showLogin() {
      document.getElementById('login-screen').classList.remove('hidden');
      document.getElementById('main-screen').classList.add('hidden');
    }

    function setCalendarConnected(connected) {
      calendarConnected = !!connected;
      const status = document.getElementById('calendar-status');
      const btn = document.getElementById('btn-connect-calendar');
      if (calendarConnected) {
        status.textContent = 'Google Calendar connected';
        btn.classList.add('hidden');
      } else {
        status.textContent = 'Google Calendar not connected';
        btn.classList.remove('hidden');
      }
    }

    function updateViewButtons() {
      const map = {
        day: document.getElementById('view-day'),
        week: document.getElementById('view-week'),
        month: document.getElementById('view-month'),
      };
      Object.entries(map).forEach(([mode, btn]) => {
        if (!btn) return;
        if (mode === viewMode) {
          btn.classList.add('btn-accent');
          btn.classList.remove('bg-white/10');
        } else {
          btn.classList.remove('btn-accent');
          btn.classList.add('bg-white/10');
        }
      });
    }

    function setViewMode(mode) {
      viewMode = mode;
      viewAnchor = new Date();
      updateViewButtons();
      loadSchedule();
    }

    function getViewRange() {
      const anchor = new Date(viewAnchor);
      anchor.setHours(0, 0, 0, 0);
      if (viewMode === 'day') {
        const end = new Date(anchor);
        end.setDate(end.getDate() + 1);
        return { start: anchor, end };
      }
      if (viewMode === 'month') {
        const monthStart = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        const gridStart = new Date(monthStart);
        gridStart.setDate(monthStart.getDate() - monthStart.getDay());
        const gridEnd = new Date(gridStart);
        gridEnd.setDate(gridEnd.getDate() + 42);
        return { start: gridStart, end: gridEnd };
      }
      const weekStart = startOfWeek(anchor);
      const end = new Date(weekStart);
      end.setDate(end.getDate() + 7);
      return { start: weekStart, end };
    }

    function dayKey(d) {
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      return `${y}-${m}-${day}`;
    }

    function startOfWeek(d) {
      const date = new Date(d);
      date.setHours(0, 0, 0, 0);
      const day = date.getDay(); // 0 = Sunday
      date.setDate(date.getDate() - day);
      return date;
    }

    function renderWeekHeader(start, days) {
      const header = document.getElementById('calendar-days-header');
      header.style.gridTemplateColumns = `64px repeat(${days}, 1fr)`;
      let html = '<div></div>';
      for (let i = 0; i < days; i++) {
        const day = new Date(start);
        day.setDate(start.getDate() + i);
        const label = day.toLocaleDateString('en-US', { weekday: 'short' });
        html += `<div class="day" data-day="${dayKey(day)}">${label}<div class="text-slate-500 text-xs">${day.getDate()}</div></div>`;
      }
      header.innerHTML = html;
    }

    function buildCalendarGrid(start, days) {
      const grid = document.getElementById('calendar-grid');
      grid.classList.remove('calendar-month');
      grid.classList.add('calendar-grid');
      grid.style.setProperty('--hour-height', `${HOUR_HEIGHT}px`);
      grid.innerHTML = '';

      const inner = document.createElement('div');
      inner.className = 'calendar-grid-inner';

      const timeCol = document.createElement('div');
      timeCol.className = 'calendar-time-col';
      for (let h = CAL_START_HOUR; h < CAL_END_HOUR; h++) {
        const label = new Date(2000, 0, 1, h, 0, 0).toLocaleTimeString([], { hour: 'numeric' });
        const t = document.createElement('div');
        t.className = 'time';
        t.textContent = label;
        timeCol.appendChild(t);
      }
      inner.appendChild(timeCol);

      const dayCols = {};
      for (let i = 0; i < days; i++) {
        const day = new Date(start);
        day.setDate(start.getDate() + i);
        const key = dayKey(day);
        const col = document.createElement('div');
        col.className = 'calendar-day-col';
        col.dataset.day = key;
        inner.appendChild(col);
        dayCols[key] = col;
      }

      grid.appendChild(inner);
      return dayCols;
    }

    function placeBlock(dayCols, start, end, className, label, opts = {}) {
      const key = dayKey(start);
      const col = dayCols[key];
      if (!col) return;

      const dayStart = new Date(start);
      dayStart.setHours(0, 0, 0, 0);
      const rangeStart = new Date(dayStart);
      rangeStart.setHours(CAL_START_HOUR, 0, 0, 0);
      const rangeEnd = new Date(dayStart);
      rangeEnd.setHours(CAL_END_HOUR, 0, 0, 0);

      const clampStart = start < rangeStart ? rangeStart : start;
      const clampEnd = end > rangeEnd ? rangeEnd : end;
      if (clampEnd <= clampStart) return;

      const minutesFromStart = (clampStart - rangeStart) / 60000;
      const duration = (clampEnd - clampStart) / 60000;
      const minuteHeight = HOUR_HEIGHT / 60;
      const top = minutesFromStart * minuteHeight;
      const height = Math.max(duration * minuteHeight, 12);

      const block = document.createElement('div');
      block.className = `calendar-block ${className}`;
      block.style.top = `${top}px`;
      block.style.height = `${height}px`;
      if (opts.html) {
        block.innerHTML = opts.html;
      } else {
        block.textContent = label;
      }
      block.title = `${start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} – ${end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
      if (opts.dataset) {
        Object.entries(opts.dataset).forEach(([k, v]) => {
          block.dataset[k] = v;
        });
      }
      col.appendChild(block);
      return block;
    }

    function parseAllDayDate(dateStr) {
      const [y, m, d] = dateStr.split('-').map(Number);
      return new Date(y, m - 1, d, 0, 0, 0);
    }

    function forEachDaySegment(start, end, cb) {
      let current = new Date(start);
      current.setHours(0, 0, 0, 0);
      while (current < end) {
        const next = new Date(current);
        next.setDate(current.getDate() + 1);
        const segStart = start > current ? start : current;
        const segEnd = end < next ? end : next;
        if (segEnd > segStart) cb(segStart, segEnd);
        current = next;
      }
    }

    function renderMonthView() {
      const grid = document.getElementById('calendar-grid');
      grid.innerHTML = '';
      grid.classList.remove('calendar-grid');
      grid.classList.add('calendar-month');

      const { start, end } = getViewRange();
      const days = Math.round((end - start) / 86400000);
      const dayMap = {};
      for (let i = 0; i < days; i++) {
        const d = new Date(start);
        d.setDate(start.getDate() + i);
        const key = dayKey(d);
        const cell = document.createElement('div');
        cell.className = 'month-cell';
        const dateLabel = document.createElement('div');
        dateLabel.className = 'date';
        dateLabel.textContent = d.getDate();
        const eventsWrap = document.createElement('div');
        eventsWrap.className = 'events';
        cell.appendChild(dateLabel);
        cell.appendChild(eventsWrap);
        grid.appendChild(cell);
        dayMap[key] = eventsWrap;
      }

      (calendarEvents || []).forEach(ev => {
        const summary = ev.summary || 'Busy';
        const allDay = !!ev.all_day;
        let s = allDay ? parseAllDayDate(ev.start) : new Date(ev.start);
        let e = allDay ? parseAllDayDate(ev.end) : new Date(ev.end);
        if (allDay && e <= s) {
          e = new Date(s);
          e.setDate(e.getDate() + 1);
        }
        forEachDaySegment(s, e, (segStart) => {
          const key = dayKey(segStart);
          const cell = dayMap[key];
          if (!cell) return;
          const chip = document.createElement('div');
          chip.className = 'month-event';
          chip.textContent = summary;
          cell.appendChild(chip);
        });
      });

      const pending = (suggestionsCache || []).filter(s => s.status === 'pending');
      pending.forEach(s => {
        const st = new Date(s.start_time);
        const key = dayKey(st);
        const cell = dayMap[key];
        if (!cell) return;
        const chip = document.createElement('div');
        chip.className = 'month-event';
        chip.textContent = 'Suggested';
        cell.appendChild(chip);
      });
    }

    function renderSchedule() {
      const empty = document.getElementById('calendar-empty');
      const { start } = getViewRange();
      const days = viewMode === 'day' ? 1 : (viewMode === 'week' ? 7 : 7);

      if (viewMode === 'month') {
        const header = document.getElementById('calendar-days-header');
        header.style.gridTemplateColumns = 'repeat(7, 1fr)';
        header.innerHTML = `
          <div class="day">Sun</div>
          <div class="day">Mon</div>
          <div class="day">Tue</div>
          <div class="day">Wed</div>
          <div class="day">Thu</div>
          <div class="day">Fri</div>
          <div class="day">Sat</div>
        `;
      } else {
        renderWeekHeader(start, days);
      }

      if (!calendarConnected) {
        empty.textContent = 'Connect Google Calendar to see your calendar.';
        empty.classList.remove('hidden');
        document.getElementById('calendar-grid').innerHTML = '';
        return;
      }

      empty.classList.add('hidden');

      if (viewMode === 'month') {
        renderMonthView();
        return;
      }

      const dayCols = buildCalendarGrid(start, days);

      (calendarBusy || []).forEach(b => {
        const s = new Date(b.start);
        const e = new Date(b.end);
        placeBlock(dayCols, s, e, 'busy', 'Busy');
      });

      (calendarEvents || []).forEach(ev => {
        const summary = ev.summary || 'Busy';
        const allDay = !!ev.all_day;
        let s = allDay ? parseAllDayDate(ev.start) : new Date(ev.start);
        let e = allDay ? parseAllDayDate(ev.end) : new Date(ev.end);
        if (allDay && e <= s) {
          e = new Date(s);
          e.setDate(e.getDate() + 1);
        }
        forEachDaySegment(s, e, (segStart, segEnd) => {
          placeBlock(dayCols, segStart, segEnd, 'event', summary, {
            html: `<div class="block-title">${escapeHtml(summary)}</div>`,
          });
        });
      });

      const pending = (suggestionsCache || []).filter(s => s.status === 'pending');
      pending.forEach(s => {
        const st = new Date(s.start_time);
        const et = new Date(s.end_time);
        const html = `
          <div class="block-title">Suggested</div>
          <div class="block-actions">
            <button class="suggestion-accept" data-id="${s.id}">Accept</button>
            <button class="suggestion-decline" data-id="${s.id}">Decline</button>
          </div>
        `;
        placeBlock(dayCols, st, et, 'suggestion', 'Suggested', { html, dataset: { suggestionId: s.id } });
      });

      document.querySelectorAll('.suggestion-accept').forEach(btn => {
        btn.onclick = (e) => {
          e.stopPropagation();
          approve(btn.dataset.id);
        };
      });
      document.querySelectorAll('.suggestion-decline').forEach(btn => {
        btn.onclick = (e) => {
          e.stopPropagation();
          reject(btn.dataset.id);
        };
      });
    }

    async function loadSchedule() {
      const { start, end } = getViewRange();
      if (!getToken()) {
        calendarEvents = [];
        calendarBusy = [];
        renderSchedule();
        return;
      }
      try {
        const res = await api(`/api/calendar/events?start=${start.toISOString()}&end=${end.toISOString()}`);
        calendarEvents = Array.isArray(res) ? res : (res.events || []);
        setCalendarConnected(true);
      } catch (e) {
        calendarEvents = [];
        if (e.status === 400 || e.status === 401 || /not connected/i.test(e.message || '')) {
          setCalendarConnected(false);
        }
      }
      if (viewMode !== 'month' && calendarConnected) {
        try {
          const busy = await api(`/api/calendar/free-busy?start=${start.toISOString()}&end=${end.toISOString()}`);
          calendarBusy = busy.busy || [];
        } catch (e) {
          calendarBusy = [];
        }
      } else {
        calendarBusy = [];
      }
      renderSchedule();
    }

    async function loadProfile() {
      if (!getToken()) return;
      const profile = await api('/api/profile');
      document.querySelector('[name="display_name"]').value = profile.display_name || '';
      const tzInput = document.querySelector('[name="timezone"]');
      if (profile.timezone === null || profile.timezone === undefined) {
        tzInput.value = '';
        tzInput.disabled = true;
        tzInput.placeholder = 'Timezone from Google Calendar';
      } else {
        tzInput.disabled = false;
        tzInput.value = profile.timezone || '';
        tzInput.placeholder = 'America/Los_Angeles';
      }
      const prefs = profile.preferences || {};
      document.querySelector('[name="profile_preferences"]').value = Object.keys(prefs).length
        ? JSON.stringify(prefs, null, 2)
        : '';
      setCalendarConnected(profile.calendar_connected);
      loadSchedule();
    }

    // profile form handler is set in setupProfileForm when the menu is rendered

    document.getElementById('btn-google').onclick = async () => {
      await sb.auth.signInWithOAuth({ provider: 'google' });
    };

    async function loadConfig() {
      const res = await fetch(`${API}/api/config`);
      if (!res.ok) throw new Error(await res.text());
      const cfg = await res.json();
      SUPABASE_URL = cfg.supabase_url || '';
      SUPABASE_ANON_KEY = cfg.supabase_publishable_key || cfg.supabase_anon_key || '';
    }

    async function initSupabase() {
      if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
        document.getElementById('login-screen').innerHTML = '<p class="text-amber-500">Missing Supabase config. Check backend /api/config and backend/.env</p>';
        return;
      }
      sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
      const { data: { session: s } } = await sb.auth.getSession();
      session = s;
      if (session) showMain(); else showLogin();
      renderAuth();
      if (session) {
        loadSchedule();
      }
      sb.auth.onAuthStateChange((e, s) => {
        session = s;
        if (session) {
          showMain();
          loadProfile();
          loadTasks();
          loadSuggestions();
          loadSchedule();
        } else {
          showLogin();
          setCalendarConnected(false);
          calendarEvents = [];
          suggestionsCache = [];
          renderSchedule();
        }
        renderAuth();
      });
    }

    document.getElementById('task-form').onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const created = await api('/api/tasks', {
        method: 'POST',
        body: JSON.stringify({
          name: fd.get('name'),
          description: fd.get('description') || '',
          difficulty: fd.get('difficulty'),
          focus_level: fd.get('focus_level'),
          time_preference: fd.get('time_preference'),
        }),
      });
      e.target.reset();
      loadTasks();
      if (created?.id) {
        await suggestSlots(created.id);
      }
    };

    async function loadTasks() {
      if (!getToken()) return;
      const tasks = await api('/api/tasks');
      const el = document.getElementById('tasks-list');
      el.innerHTML = tasks.map(t => `
        <div class="p-3 card flex justify-between items-center">
          <div>
            <span class="font-medium text-[var(--text)]">${escapeHtml(t.name)}</span>
            <span class="text-[var(--muted)] text-sm ml-2">${t.focus_level} · ${t.time_preference}</span>
          </div>
          <button data-task-id="${t.id}" class="suggest-slots px-3 py-1.5 text-sm btn-accent pill">Suggest slots</button>
        </div>
      `).join('');
      el.querySelectorAll('.suggest-slots').forEach(btn => {
        btn.onclick = () => suggestSlots(btn.dataset.taskId);
      });
    }

    function escapeHtml(s) {
      const d = document.createElement('div');
      d.textContent = s;
      return d.innerHTML;
    }

    async function suggestSlots(taskId) {
      const start = new Date();
      start.setHours(0,0,0,0);
      const end = new Date(start);
      end.setDate(end.getDate() + 7);
      try {
        await api(`/api/suggestions/suggest/${taskId}?start=${start.toISOString()}&end=${end.toISOString()}`);
        loadSuggestions();
      } catch (e) {
        alert(e.message || 'Failed (connect Google Calendar first)');
      }
    }

    async function loadSuggestions() {
      const list = await api('/api/suggestions');
      suggestionsCache = list;
      const pending = list.filter(s => s.status === 'pending');
      const el = document.getElementById('suggestions-list');
      const empty = document.getElementById('suggestions-empty');
      if (pending.length === 0) {
        el.innerHTML = '';
        empty.classList.remove('hidden');
        renderSchedule();
        return;
      }
        empty.classList.add('hidden');
        el.innerHTML = pending.map(s => {
          const start = new Date(s.start_time);
          const end = new Date(s.end_time);
          const label = `${start.toLocaleDateString()} ${start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} – ${end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
          return `
          <div class="p-3 card flex justify-between items-center gap-2" data-id="${s.id}">
            <span class="text-xs truncate text-[var(--text)]">${label}</span>
            <span class="flex gap-1">
              <button class="approve px-2 py-1 text-xs btn-accent pill">Add</button>
              <button class="reject px-2 py-1 text-xs pill bg-[var(--panel-border)] text-[var(--text)]">Reject</button>
            </span>
          </div>
        `;
        }).join('');
      el.querySelectorAll('.approve').forEach(btn => {
        btn.onclick = () => approve(btn.closest('[data-id]').dataset.id);
      });
      el.querySelectorAll('.reject').forEach(btn => {
        btn.onclick = () => reject(btn.closest('[data-id]').dataset.id);
      });
      renderSchedule();
    }

    async function approve(id) {
      await api(`/api/suggestions/${id}/approve`, { method: 'POST', body: JSON.stringify({ add_to_calendar: true }) });
      await loadSuggestions();
      await loadSchedule();
    }

    async function reject(id) {
      await api(`/api/suggestions/${id}/reject`, { method: 'POST' });
      await loadSuggestions();
    }

    document.getElementById('btn-connect-calendar').onclick = (e) => {
      e.preventDefault();
      const token = getToken();
      if (!token) { alert('Sign in first.'); return; }
      window.location.href = `${API}/api/auth/google/connect?access_token=${encodeURIComponent(token)}`;
    };

    document.getElementById('view-day').onclick = () => setViewMode('day');
    document.getElementById('view-week').onclick = () => setViewMode('week');
    document.getElementById('view-month').onclick = () => setViewMode('month');
    updateViewButtons();
    renderSchedule();

    // URL params
    const params = new URLSearchParams(location.search);
    if (params.get('calendar_connected') === '1') {
      setCalendarConnected(true);
      loadSchedule();
      history.replaceState({}, '', location.pathname);
    }
    if (params.get('calendar_error') === '1') {
      setCalendarConnected(false);
      document.getElementById('calendar-status').textContent = 'Calendar connection failed';
      renderSchedule();
      history.replaceState({}, '', location.pathname);
    }

    loadConfig()
      .then(initSupabase)
      .then(() => {
        if (session) {
          loadProfile();
          loadTasks();
          loadSuggestions();
        }
      })
      .catch((e) => {
        document.getElementById('login-screen').innerHTML = `<p class="text-amber-500">${e.message || 'Failed to load config'}</p>`;
      });
