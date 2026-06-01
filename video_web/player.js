/* ============================================================
   Course Player — player.js
   Requires course.js loaded first (window.COURSE_DATA)
   ============================================================ */
(function () {
  'use strict';

  // ── Helpers ────────────────────────────────────────────────
  const $ = id => document.getElementById(id);

  // ── DOM refs ───────────────────────────────────────────────
  const avatarVideo = $('avatar-video');
  const mainVideo = $('main-video');
  const mainImage = $('main-image');
  const subtitleOverlay = $('subtitle-overlay');
  const navList = $('nav-list');
  const courseTitleEl = $('course-title');
  const slideCounterEl = $('slide-counter');
  const btnPlay = $('btn-play');
  const btnPrev = $('btn-prev');
  const btnNext = $('btn-next');
  const btnMute = $('btn-mute');
  const progressTrack = $('progress-track');
  const progressFill = $('progress-fill');
  const progressThumb = $('progress-thumb');
  const timeDisplay = $('time-display');
  const globalProgressEl = $('global-progress');
  const volSlider = $('vol-slider');

  // ── State ──────────────────────────────────────────────────
  let course = null;
  let currentIndex = 0;
  let isPlaying = false;
  let isSeeking = false;
  let currentType = 'image'; // 'image' | 'video' | 'avatar'
  let frames = null;    // current slide's frames array, or null
  let frameOffsets = [];      // precomputed start times in seconds
  let currentFrameIdx = 0;
  let slideDurations = [];    // duration (seconds) per slide index, null until loaded
  let pendingAdvance = null;  // setTimeout id for the post-slide auto-advance
  let activeTrack = null;     // current VTT TextTrack

  // ── Init ───────────────────────────────────────────────────
  function init() {
    course = window.COURSE_DATA;
    if (!course || !course.slides || !course.slides.length) {
      console.error('[Player] No COURSE_DATA found. Make sure course.js is loaded.');
      return;
    }

    document.title = course.course;
    courseTitleEl.textContent = course.course;

    extractTheme(course.theme || 'assets/theme.jpg');
    if (course.audioOnly) {
      document.body.classList.add('audio-only');
    }
    buildNav();
    bindControls();
    slideDurations = new Array(course.slides.length).fill(null);
    preloadAllDurations();
    const urlParams = new URLSearchParams(window.location.search);
    const slideParam = parseInt(urlParams.get('slide'), 10);
    const startIndex = (!isNaN(slideParam) && slideParam >= 1)
      ? Math.min(slideParam - 1, course.slides.length - 1)
      : 0;

    // If a slide param is present, user came from quiz results — update back button
    if (!isNaN(slideParam) && slideParam >= 1) {
      const persona = urlParams.get('persona') || '';
      const btnBack = $('btn-back');
      if (btnBack && persona) {
        btnBack.href = 'quiz.html?persona=' + encodeURIComponent(persona) + '&results=1';
        btnBack.title = 'Back to Quiz Results';
      }
    }

    loadSlide(startIndex, false);

    requestAnimationFrame(progressLoop);
  }

  // ── Global duration preload ─────────────────────────────────
  function preloadAllDurations() {
    course.slides.forEach(function (slide, i) {
      if (slide.frames) {
        slideDurations[i] = slide.frames.reduce(function (sum, f) { return sum + (f.duration || 0); }, 0);
        return;
      }
      const v = document.createElement('video');
      v.preload = 'metadata';
      v.src = slide.avatar || '';
      v.addEventListener('loadedmetadata', function () {
        slideDurations[i] = v.duration;
      });
    });
  }

  // ── Theme extraction ───────────────────────────────────────
  function extractTheme(src) {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = function () {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = 24;
        canvas.height = 24;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, 24, 24);
        const data = ctx.getImageData(0, 0, 24, 24).data;

        let maxSat = 0, ar = 124, ag = 106, ab = 247;
        for (let i = 0; i < data.length; i += 4) {
          const r = data[i], g = data[i + 1], b = data[i + 2];
          const max = Math.max(r, g, b), min = Math.min(r, g, b);
          const lum = (max + min) / 510;
          const sat = max === 0 ? 0 : (max - min) / max;
          if (sat > maxSat && lum > 0.15 && lum < 0.85) {
            maxSat = sat; ar = r; ag = g; ab = b;
          }
        }

        if (maxSat > 0.25) {
          const root = document.documentElement;
          root.style.setProperty('--accent', `rgb(${ar},${ag},${ab})`);
          root.style.setProperty('--accent-dark', `rgb(${Math.round(ar * 0.55)},${Math.round(ag * 0.55)},${Math.round(ab * 0.55)})`);
          root.style.setProperty('--accent-light', `rgb(${clamp(Math.round(ar * 1.35))},${clamp(Math.round(ag * 1.35))},${clamp(Math.round(ab * 1.35))})`);
          root.style.setProperty('--accent-glow', `rgba(${ar},${ag},${ab},0.28)`);
        }
      } catch (_) { /* CORS or canvas tainted — use defaults */ }
    };
    img.onerror = () => { };
    img.src = src;
  }

  function clamp(v) { return Math.min(255, Math.max(0, v)); }

  // ── Navigation ─────────────────────────────────────────────
  function buildNav() {
    navList.innerHTML = '';
    course.slides.forEach((slide, i) => {
      const li = document.createElement('li');
      li.dataset.index = i;

      const depth = (slide.id.match(/\./g) || []).length;
      if (depth > 0) li.classList.add('nav-sub', 'nav-depth-' + depth);

      const num = document.createElement('span');
      num.className = 'nav-num';
      num.textContent = slide.id;

      const title = document.createElement('span');
      title.className = 'nav-title';
      title.textContent = slide.title;

      li.appendChild(num);
      li.appendChild(title);

      li.addEventListener('click', () => {
        loadSlide(i, true);
      });

      navList.appendChild(li);
    });
  }

  function updateNav(index) {
    navList.querySelectorAll('li').forEach(li => {
      const i = parseInt(li.dataset.index, 10);
      li.classList.toggle('active', i === index);
      li.classList.toggle('done', i < index);
    });
    const active = navList.querySelector('li.active');
    if (active) active.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  // ── Load slide ─────────────────────────────────────────────
  function loadSlide(index, autoplay) {
    if (pendingAdvance) { clearTimeout(pendingAdvance); pendingAdvance = null; }
    doPause(); // Force stop to avoid audio overlap
    clearSubtitles();

    progressFill.style.width = '0%';
    progressThumb.style.left = '0%';
    timeDisplay.textContent = '0:00 / 0:00';

    currentIndex = index;
    const slide = course.slides[index];
    const src = slide.main ? (slide.main.src || '') : '';
    const declaredType = slide.main ? slide.main.type : null;

    // Reset frame state
    frames = slide.frames || null;
    frameOffsets = [];
    currentFrameIdx = 0;

    updateNav(index);
    slideCounterEl.textContent = `${index + 1} / ${course.slides.length}`;

    if (frames) {
      // ── Multi-frame slide: avatar in left, images cycle in main ──
      currentType = 'image';
      let t = 0;
      for (const f of frames) {
        frameOffsets.push(t);
        t += (f.duration || Infinity);
      }
      avatarVideo.src = slide.avatar || '';
      avatarVideo.load();
      avatarVideo.classList.remove('blank');
      mainVideo.classList.add('hidden');
      mainImage.classList.remove('hidden');
      loadSubtitles(slide.avatar, avatarVideo);
      mainImage.src = frames[0].src;
    } else {
      // ── Auto-detect layout: no src → avatar fullscreen in main area ──
      currentType = !src ? 'avatar' : declaredType === 'video' ? 'video' : 'image';

      // ── Avatar slot (left panel) ──
      if (currentType === 'avatar') {
        avatarVideo.src = '';
        avatarVideo.classList.add('blank');
      } else {
        // Append <track> BEFORE assigning src so the browser binds it
        // when it starts loading the new video.
        loadSubtitles(slide.avatar, avatarVideo);
        avatarVideo.src = slide.avatar || '';
        avatarVideo.load();
        avatarVideo.classList.toggle('blank', currentType === 'video');
      }

      // ── Main content ──
      if (currentType === 'video') {
        mainVideo.src = src;
        mainVideo.muted = slide.main.muted !== false;
        mainVideo.load();
        mainVideo.classList.remove('hidden');
        mainImage.classList.add('hidden');
      } else if (currentType === 'avatar') {
        loadSubtitles(slide.avatar, mainVideo);
        mainVideo.src = slide.avatar || '';
        mainVideo.muted = false;
        mainVideo.load();
        mainVideo.classList.remove('hidden');
        mainImage.classList.add('hidden');
      } else {
        mainVideo.classList.add('hidden');
        mainImage.classList.remove('hidden');
        mainImage.src = src;
      }
    }

    if (autoplay !== false) {
      doPlay(true); // fresh slide — start from 0
    }
  }

  // ── Playback ───────────────────────────────────────────────
  // Always call play() immediately so the browser starts buffering. For a
  // fresh slide load, anchor currentTime to 0 (now and again on metadata load)
  // to avoid the phantom-playback drift that happens when play() races with
  // a freshly-set src. If play() rejects (load race), retry once the element
  // is ready. `resetTime` should be true on a fresh slide load and false when
  // resuming after a manual pause.
  function safePlay(vid, resetTime) {
    if (resetTime) {
      try { vid.currentTime = 0; } catch (e) { /* may throw if not seekable yet */ }
      vid.addEventListener('loadedmetadata', function reset() {
        try { vid.currentTime = 0; } catch (e) { }
      }, { once: true });
    }
    paintBar(vid);
    const p = vid.play();
    if (p) p.catch(function () {
      const retry = function () {
        const r = vid.play();
        if (r) r.catch(() => { });
      };
      vid.addEventListener('canplay', retry, { once: true });
      vid.addEventListener('loadeddata', retry, { once: true });
    });
  }

  function doPlay(resetTime) {
    if (currentType === 'avatar') {
      // Avatar plays fullscreen in main area — only mainVideo runs
      safePlay(mainVideo, resetTime);
    } else {
      safePlay(avatarVideo, resetTime);
      if (currentType === 'video') {
        safePlay(mainVideo, resetTime);
      }
    }
    isPlaying = true;
    updatePlayBtn();
  }

  function doPause() {
    avatarVideo.pause();
    mainVideo.pause();
    isPlaying = false;
    updatePlayBtn();
  }

  function togglePlayPause() {
    if (isPlaying) doPause();
    else doPlay(false); // resume from current position
  }

  function updatePlayBtn() {
    btnPlay.innerHTML = isPlaying ? '&#9646;&#9646;' : '&#9654;';
    btnPlay.title = isPlaying ? 'Pause (Space)' : 'Play (Space)';
  }

  // Keep state in sync when browser pauses/plays
  avatarVideo.addEventListener('play', () => { if (currentType !== 'avatar') { isPlaying = true; updatePlayBtn(); } });
  avatarVideo.addEventListener('pause', () => { if (currentType !== 'avatar') { isPlaying = false; updatePlayBtn(); } });
  mainVideo.addEventListener('play', () => { if (currentType === 'avatar') { isPlaying = true; updatePlayBtn(); } });
  mainVideo.addEventListener('pause', () => { if (currentType === 'avatar') { isPlaying = false; updatePlayBtn(); } });

  // Drive the progress bar directly from each video's timeupdate / loadedmetadata.
  // This is more reliable than the rAF guard, which can miss updates when
  // currentType is briefly stale during slide transitions.
  function paintBar(vid) {
    if (!vid.duration || isNaN(vid.duration)) return;
    const rawPct = (vid.currentTime / vid.duration) * 100;
    // Floor at a minimum visible width once playback has started, so slow-
    // growing progress on long slides is still perceptible from the first
    // second instead of looking like an empty bar.
    let pct = rawPct;
    if (vid.currentTime > 0) {
      const trackW = progressTrack.offsetWidth || 1;
      const minPct = (6 / trackW) * 100;
      if (pct < minPct) pct = minPct;
    }
    progressFill.style.width = pct + '%';
    progressThumb.style.left = pct + '%';
    timeDisplay.textContent = fmtTime(vid.currentTime) + ' / ' + fmtTime(vid.duration);
  }
  function isActiveVid(vid) {
    return vid === (currentType === 'avatar' ? mainVideo : avatarVideo);
  }
  ['timeupdate', 'loadedmetadata', 'durationchange', 'seeked', 'play', 'playing', 'progress'].forEach(function (evt) {
    avatarVideo.addEventListener(evt, function () { if (isActiveVid(avatarVideo)) paintBar(avatarVideo); });
    mainVideo.addEventListener(evt, function () { if (isActiveVid(mainVideo)) paintBar(mainVideo); });
  });

  // ── Auto-advance ────────────────────────────────────────────
  function onSlideEnded() {
    if (currentIndex >= course.slides.length - 1) {
      // Last slide ended — check if a quiz exists, then wait 5s before
      // navigating so the completion message has a moment to land.
      const persona = new URLSearchParams(window.location.search).get('persona') || '';
      if (!persona) return; // no persona, stay put
      fetch(persona + '/quiz.json', { method: 'HEAD' })
        .then(function (r) {
          if (r.ok) {
            pendingAdvance = setTimeout(function () {
              pendingAdvance = null;
              window.location.href = 'quiz.html?persona=' + encodeURIComponent(persona);
            }, 2000);
          }
          // no quiz file — stay on the last slide
        })
        .catch(function () {
          // network error — stay on the last slide
        });
      return;
    }
    pendingAdvance = setTimeout(function () {
      pendingAdvance = null;
      loadSlide(currentIndex + 1, true);
    }, 1000);
  }

  avatarVideo.addEventListener('ended', function () {
    if (currentType !== 'avatar') onSlideEnded();
  });

  mainVideo.addEventListener('ended', function () {
    if (currentType === 'avatar') onSlideEnded();
  });

  // ── Progress loop (rAF) ─────────────────────────────────────
  function progressLoop() {
    const timeVid = currentType === 'avatar' ? mainVideo : avatarVideo;
    if (timeVid.duration) paintBar(timeVid);

    // ── Global course progress ──
    const allLoaded = slideDurations.every(function (d) { return d !== null; });
    let offset = 0;
    for (let i = 0; i < currentIndex; i++) {
      offset += slideDurations[i] || 0;
    }
    const globalNow = offset + (timeVid.currentTime || 0);
    const globalTotal = slideDurations.reduce(function (s, d) { return s + (d || 0); }, 0);
    globalProgressEl.textContent = fmtTime(globalNow) + ' / ' + (allLoaded ? fmtTime(globalTotal) : '--:--');

    // ── Frame cycling (also handles seek correction) ──
    if (frames && frames.length > 1) {
      const t = avatarVideo.currentTime;
      for (let i = frameOffsets.length - 1; i >= 0; i--) {
        if (t >= frameOffsets[i]) {
          if (i !== currentFrameIdx) {
            currentFrameIdx = i;
            mainImage.src = frames[i].src;
          }
          break;
        }
      }
    }

    requestAnimationFrame(progressLoop);
  }

  function fmtTime(s) {
    if (!s || isNaN(s)) return '0:00';
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60).toString().padStart(2, '0');
    return `${m}:${sec}`;
  }

  // ── Seek (click + drag on progress bar) ────────────────────
  progressTrack.addEventListener('mousedown', function (e) {
    isSeeking = true;
    applySeek(e);
  });

  document.addEventListener('mousemove', function (e) {
    if (isSeeking) applySeek(e);
  });

  document.addEventListener('mouseup', function () {
    isSeeking = false;
  });

  function applySeek(e) {
    const rect = progressTrack.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    if (currentType === 'avatar') {
      if (mainVideo.duration) mainVideo.currentTime = pct * mainVideo.duration;
    } else {
      if (avatarVideo.duration) avatarVideo.currentTime = pct * avatarVideo.duration;
      if (currentType === 'video' && mainVideo.duration) {
        mainVideo.currentTime = pct * mainVideo.duration;
      }
    }
    progressFill.style.width = (pct * 100) + '%';
    progressThumb.style.left = (pct * 100) + '%';
  }

  // ── Controls ───────────────────────────────────────────────
  function bindControls() {
    btnPlay.addEventListener('click', togglePlayPause);

    btnPrev.addEventListener('click', function () {
      if (currentIndex > 0) loadSlide(currentIndex - 1, true);
    });

    btnNext.addEventListener('click', function () {
      if (currentIndex < course.slides.length - 1) loadSlide(currentIndex + 1, true);
    });

    volSlider.addEventListener('input', function () {
      const v = parseFloat(volSlider.value);
      avatarVideo.volume = v;
      mainVideo.volume = v;
      avatarVideo.muted = false;
      mainVideo.muted = false;
      updateMuteBtn(v);
    });

    btnMute.addEventListener('click', function () {
      const muted = !avatarVideo.muted;
      avatarVideo.muted = muted;
      mainVideo.muted = muted;
      updateMuteBtn(muted ? 0 : avatarVideo.volume);
    });

    document.addEventListener('keydown', function (e) {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (e.code === 'Space') {
        e.preventDefault();
        togglePlayPause();
      } else if (e.code === 'ArrowRight') {
        if (currentIndex < course.slides.length - 1) loadSlide(currentIndex + 1, true);
      } else if (e.code === 'ArrowLeft') {
        if (currentIndex > 0) loadSlide(currentIndex - 1, true);
      }
    });
  }

  function updateMuteBtn(volume) {
    const muted = currentType === 'avatar' ? mainVideo.muted : avatarVideo.muted;
    if (volume === 0 || muted) {
      btnMute.innerHTML = '&#128263;';
    } else if (volume < 0.5) {
      btnMute.innerHTML = '&#128264;';
    } else {
      btnMute.innerHTML = '&#128266;';
    }
  }

  // ── Subtitles ─────────────────────────────────────────────
  let subtitlePollId = null;

  function clearSubtitles() {
    subtitleOverlay.textContent = '';
    subtitleOverlay.classList.remove('visible');
    if (activeTrack) {
      activeTrack.removeEventListener('cuechange', onCueChange);
    }
    activeTrack = null;
    if (subtitlePollId) {
      clearInterval(subtitlePollId);
      subtitlePollId = null;
    }
    // Remove any existing track elements
    document.querySelectorAll('#avatar-video track, #main-video track').forEach(t => t.remove());
  }

  function loadSubtitles(avatarSrc, videoEl) {
    if (!avatarSrc) return;
    // Derive VTT path from avatar video path: videos/Slide_X.mp4 -> videos/Slide_X.vtt
    const vttSrc = avatarSrc.replace(/\.(mp4|mp3)$/i, '.vtt');

    const track = document.createElement('track');
    track.kind = 'subtitles';
    track.label = 'English';
    track.srclang = 'en';
    // Cache-bust: <track> elements are aggressively cached and ignore normal
    // hard-reload, so append a per-load query so the VTT is always re-fetched.
    track.src = vttSrc + '?v=' + Date.now();
    track.default = true;
    videoEl.appendChild(track);

    // track.track is available synchronously after append. Setting mode to
    // 'hidden' forces the browser to begin fetching the .vtt immediately
    // (without it, some browsers defer loading).
    if (track.track) {
      activeTrack = track.track;
      activeTrack.mode = 'hidden';
      activeTrack.addEventListener('cuechange', onCueChange);
    }

    // The .vtt arrives async; force a first paint as soon as it's parsed.
    track.addEventListener('load', onCueChange);
  }

  function onCueChange() {
    if (!activeTrack || !activeTrack.activeCues || activeTrack.activeCues.length === 0) {
      subtitleOverlay.classList.remove('visible');
      return;
    }
    const cue = activeTrack.activeCues[0];
    subtitleOverlay.textContent = cue.text;
    subtitleOverlay.classList.add('visible');
  }

  // ── Start ──────────────────────────────────────────────────
  // course.js now loads JSON asynchronously and fires 'courseDataReady'
  function tryInit() {
    if (window.COURSE_DATA) {
      init();
    } else {
      window.addEventListener('courseDataReady', init, { once: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryInit);
  } else {
    tryInit();
  }

})();
