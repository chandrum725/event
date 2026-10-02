/* ==========================================================================
   EVENTORA – Event Management Website
   Vanilla JavaScript · no libraries · shared by all three pages

   FEATURES
    0. SVG icon sprite (injected once, used via <use href="#icon-name">)
    1. Light / Dark theme + localStorage
    2. Sticky header state + mobile hamburger menu
    3. Active navigation link (+ scroll-spy for the Contact link)
    4. Smooth scrolling for in-page links
    5. Back-to-top button
    6. Scroll-reveal animations
    7. Animated statistics counters
    8. Social media popup (keyboard friendly, focus trapped)
    9. Gallery category filter (photos and films)
   10. Gallery lightbox for photos and films, with previous / next (built entirely in JS)
   11. Gallery items published from the admin panel (Flask API + MySQL), with
        loading preview tiles while the API is thinking
   12. Google Map placeholder handling
   13. Footer year
   14. Mouse flash effects (pointer glow, card spotlight, click flash, hero beams)
   15. Page preview (loading overlay, on every page and between pages)
   ========================================================================== */

(function () {
  'use strict';

  /* ------------------------------------------------------------------------
     Helpers
     ------------------------------------------------------------------------ */
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));

  const root = document.documentElement;
  const hasIO = 'IntersectionObserver' in window;
  const reducedMotion = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  /** Keeps Tab / Shift+Tab inside `container` (used by the popup and lightbox). */
  function trapFocus(event, container) {
    if (event.key !== 'Tab') return;
    const focusable = $$('a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])', container)
      .filter((el) => !el.hidden);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  /** Small inline-SVG string for icons created from JavaScript. */
  const iconSvg = (name) =>
    '<svg class="icon" aria-hidden="true" focusable="false"><use href="#icon-' + name + '"></use></svg>';

  /** Re-runs the gallery filter after section 11 adds items (set by initGalleryFilter). */
  let refreshGalleryFilter = () => {};


  /* ------------------------------------------------------------------------
     0. SVG ICON SPRITE
     Icons live here once instead of being copied into every HTML page.
     Use them anywhere with:
       <svg class="icon" aria-hidden="true"><use href="#icon-heart"></use></svg>
     ------------------------------------------------------------------------ */
  const ICONS = {
    sun: '<circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>',
    moon: '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    'chevron-left': '<path d="m15 18-6-6 6-6"/>',
    'chevron-right': '<path d="m9 18 6-6-6-6"/>',
    'arrow-up': '<path d="M12 19V5M5 12l7-7 7 7"/>',
    'arrow-up-right': '<path d="M7 17 17 7M7 7h10v10"/>',
    maximize: '<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    phone: '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>',
    mail: '<path d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><path d="m22 6-10 7L2 6"/>',
    'map-pin': '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
    clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    share: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.59 13.51 6.83 3.98M15.41 6.51l-6.82 3.98"/>',
    whatsapp: '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>',
    instagram: '<rect x="2" y="2" width="20" height="20" rx="5"/><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/><path d="M17.5 6.5h.01"/>',
    youtube: '<path d="M22.54 6.42a2.78 2.78 0 0 0-1.94-2C18.88 4 12 4 12 4s-6.88 0-8.6.46a2.78 2.78 0 0 0-1.94 2A29 29 0 0 0 1 11.75a29 29 0 0 0 .46 5.33A2.78 2.78 0 0 0 3.4 19c1.72.46 8.6.46 8.6.46s6.88 0 8.6-.46a2.78 2.78 0 0 0 1.94-2 29 29 0 0 0 .46-5.25 29 29 0 0 0-.46-5.33z"/><path d="m9.75 15.02 5.75-3.27-5.75-3.27z"/>',
    linkedin: '<path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-4 0v7h-4v-7a6 6 0 0 1 6-6z"/><rect x="2" y="9" width="4" height="12"/><circle cx="4" cy="4" r="2"/>',
    heart: '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>',
    briefcase: '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
    gift: '<path d="M20 12v10H4V12"/><rect x="2" y="7" width="20" height="5"/><path d="M12 22V7"/><path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z"/><path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"/>',
    music: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    gem: '<path d="M6 3h12l4 6-10 13L2 9z"/><path d="M11 3 8 9l4 13 4-13-3-6"/><path d="M2 9h20"/>',
    camera: '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
    sparkles: '<path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.14-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5l1.58-6.14a.5.5 0 0 1 .96 0L14.06 8.5A2 2 0 0 0 15.5 9.94l6.14 1.58a.5.5 0 0 1 0 .96L15.5 14.06a2 2 0 0 0-1.44 1.44l-1.58 6.14a.5.5 0 0 1-.96 0z"/><path d="M20 3v4M22 5h-4"/>',
    utensils: '<path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3zm0 0v7"/>',
    users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    lightbulb: '<path d="M9 18h6M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"/>',
    tag: '<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><path d="M7 7h.01"/>',
    target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    play: '<path d="M8 5.6v12.8L19 12z"/>'
  };

  function injectSprite() {
    if ($('#icon-sprite')) return;
    const symbols = Object.keys(ICONS)
      .map((name) => '<symbol id="icon-' + name + '" viewBox="0 0 24 24">' + ICONS[name] + '</symbol>')
      .join('');
    document.body.insertAdjacentHTML(
      'afterbegin',
      '<svg id="icon-sprite" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" ' +
      'style="position:absolute;width:0;height:0;overflow:hidden">' + symbols + '</svg>'
    );
  }


  /* ------------------------------------------------------------------------
     1. LIGHT / DARK THEME
     A tiny inline script in each page's <head> applies the saved theme before
     first paint (no flash). This module handles the toggle button itself.
     ------------------------------------------------------------------------ */
  const THEME_KEY = 'eventora-theme';
  const THEME_COLORS = { light: '#F9FAFB', dark: '#111827' };

  function readStoredTheme() {
    try { return localStorage.getItem(THEME_KEY); } catch (e) { return null; }
  }

  function applyTheme(theme, save) {
    root.setAttribute('data-theme', theme);

    const toggle = $('#theme-toggle');
    if (toggle) {
      toggle.setAttribute('aria-label', theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
    }
    const meta = $('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', THEME_COLORS[theme]);

    if (save) {
      try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* storage blocked – ignore */ }
    }
  }

  function initTheme() {
    // Sync the button label with whatever theme the <head> script applied.
    applyTheme(root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light', false);

    const toggle = $('#theme-toggle');
    if (!toggle) return;

    toggle.addEventListener('click', () => {
      const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      // Adds a short-lived class so colours cross-fade smoothly (see CSS section 01).
      root.classList.add('theme-animating');
      applyTheme(next, true);
      window.setTimeout(() => root.classList.remove('theme-animating'), 550);
    });
  }


  /* ------------------------------------------------------------------------
     2. STICKY HEADER + MOBILE HAMBURGER MENU
     ------------------------------------------------------------------------ */
  function initHeader() {
    const header = $('#site-header');
    const navToggle = $('#nav-toggle');
    const nav = $('#primary-nav');

    // Sticky positioning is pure CSS; this only adds the "scrolled" shadow.
    if (header) {
      let ticking = false;
      const update = () => {
        header.classList.toggle('is-scrolled', (window.scrollY || root.scrollTop) > 10);
        ticking = false;
      };
      window.addEventListener('scroll', () => {
        if (!ticking) { window.requestAnimationFrame(update); ticking = true; }
      }, { passive: true });
      update();
    }

    if (!navToggle || !nav) return;

    const isOpen = () => nav.classList.contains('is-open');
    const setOpen = (open) => {
      nav.classList.toggle('is-open', open);
      navToggle.setAttribute('aria-expanded', String(open));
      navToggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    };

    navToggle.addEventListener('click', () => setOpen(!isOpen()));

    // Close when a link is chosen, when clicking outside, or on Escape.
    nav.addEventListener('click', (e) => { if (e.target.closest('a')) setOpen(false); });
    document.addEventListener('click', (e) => {
      if (isOpen() && !e.target.closest('.site-header')) setOpen(false);
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && isOpen()) { setOpen(false); navToggle.focus(); }
    });

    // Reset when the viewport grows past the mobile breakpoint.
    window.addEventListener('resize', () => { if (window.innerWidth > 768 && isOpen()) setOpen(false); });
  }


  /* ------------------------------------------------------------------------
     3. ACTIVE NAVIGATION LINK
     <body data-page="home|events|company"> decides the current page. When the
     #contact section scrolls into view, the Contact link takes over.
     ------------------------------------------------------------------------ */
  function initActiveNav() {
    const page = document.body.getAttribute('data-page');
    const links = $$('.nav-link');

    const setActive = (name) => {
      links.forEach((link) => {
        const active = link.getAttribute('data-page') === name;
        link.classList.toggle('active', active);
        if (active) link.setAttribute('aria-current', name === 'contact' ? 'location' : 'page');
        else link.removeAttribute('aria-current');
      });
    };
    setActive(page);

    const contact = $('#contact');
    if (contact && hasIO) {
      new IntersectionObserver((entries) => {
        entries.forEach((entry) => setActive(entry.isIntersecting ? 'contact' : page));
      }, { rootMargin: '-45% 0px -45% 0px' }).observe(contact);
    }
  }


  /* ------------------------------------------------------------------------
     4. SMOOTH SCROLLING
     Handles links that point to an element on the current page. The sticky
     header offset comes from `scroll-padding-top` in the CSS.
     ------------------------------------------------------------------------ */
  function initSmoothScroll() {
    const normalise = (path) => path.replace(/index\.html$/, '').replace(/\/$/, '');

    document.addEventListener('click', (e) => {
      const link = e.target.closest('a[href*="#"]');
      if (!link || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      if (link.target && link.target !== '_self') return;

      let url;
      try { url = new URL(link.href, window.location.href); } catch (err) { return; }
      if (url.origin !== window.location.origin || normalise(url.pathname) !== normalise(window.location.pathname)) return;

      const id = decodeURIComponent(url.hash.slice(1));
      const target = id ? document.getElementById(id) : null;
      if (!target) return;

      e.preventDefault();
      target.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
      try { window.history.pushState(null, '', '#' + id); } catch (err) { /* file:// may block this */ }

      // Move keyboard focus to the section so screen-reader / keyboard users follow along.
      target.setAttribute('tabindex', '-1');
      target.focus({ preventScroll: true });
    });
  }


  /* ------------------------------------------------------------------------
     5. BACK-TO-TOP BUTTON
     ------------------------------------------------------------------------ */
  function initBackToTop() {
    const button = $('#back-to-top');
    if (!button) return;

    let ticking = false;
    const update = () => {
      button.classList.toggle('is-visible', (window.scrollY || root.scrollTop) > 600);
      ticking = false;
    };
    window.addEventListener('scroll', () => {
      if (!ticking) { window.requestAnimationFrame(update); ticking = true; }
    }, { passive: true });
    update();

    button.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: reducedMotion ? 'auto' : 'smooth' });
    });
  }


  /* ------------------------------------------------------------------------
     6. SCROLL-REVEAL ANIMATIONS
     - Add class="reveal" to any element, or data-stagger to a container to
       reveal its children one after another.
     - Once revealed, the helper classes are removed so they never fight with
       hover transitions.
     ------------------------------------------------------------------------ */
  function initReveal() {
    $$('[data-stagger]').forEach((group) => {
      Array.from(group.children).forEach((child, i) => {
        child.classList.add('reveal');
        child.style.setProperty('--delay', (i % 4) * 90 + 'ms');
      });
    });

    const items = $$('.reveal');
    if (!items.length) return;

    if (!hasIO || reducedMotion) {
      items.forEach((el) => el.classList.remove('reveal'));
      return;
    }

    const observer = new IntersectionObserver((entries, obs) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const el = entry.target;
        el.classList.add('is-visible');
        obs.unobserve(el);
        window.setTimeout(() => el.classList.remove('reveal', 'is-visible'), 1300);
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });

    items.forEach((el) => observer.observe(el));
  }


  /* ------------------------------------------------------------------------
     7. ANIMATED STATISTICS COUNTERS
     HTML: <span class="counter" data-target="500">500</span>
     The real number stays in the markup, so it is correct without JavaScript.
     ------------------------------------------------------------------------ */
  function initCounters() {
    const counters = $$('.counter');
    if (!counters.length || !hasIO || reducedMotion) return;

    const animate = (el) => {
      const target = parseInt(el.getAttribute('data-target'), 10) || 0;
      const duration = 2000;
      const start = performance.now();

      const tick = (now) => {
        const progress = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 4);           // ease-out quart
        el.textContent = Math.round(target * eased).toLocaleString('en-IN');
        if (progress < 1) window.requestAnimationFrame(tick);
      };
      window.requestAnimationFrame(tick);
    };

    const observer = new IntersectionObserver((entries, obs) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        animate(entry.target);
        obs.unobserve(entry.target);
      });
    }, { threshold: 0.6 });

    counters.forEach((el) => { el.textContent = '0'; observer.observe(el); });
  }


  /* ------------------------------------------------------------------------
     8. SOCIAL MEDIA POPUP ("Connect With Us")
     Opened by #social-toggle or any element with [data-open-social].
     Closes with the X button, a click on the backdrop, or Escape.
     ------------------------------------------------------------------------ */
  function initSocialPopup() {
    const popup = $('#social-popup');
    const mainToggle = $('#social-toggle');
    if (!popup) return;

    const card = $('.social-popup__card', popup);
    let lastFocused = null;

    const isOpen = () => popup.classList.contains('is-open');

    function open() {
      if (isOpen()) return;
      lastFocused = document.activeElement;
      popup.classList.add('is-open');
      popup.setAttribute('aria-hidden', 'false');
      if (mainToggle) mainToggle.setAttribute('aria-expanded', 'true');
      window.setTimeout(() => { const first = $('.social-popup__close', popup); if (first) first.focus(); }, 40);
    }

    function close() {
      if (!isOpen()) return;
      popup.classList.remove('is-open');
      popup.setAttribute('aria-hidden', 'true');
      if (mainToggle) mainToggle.setAttribute('aria-expanded', 'false');
      if (lastFocused && typeof lastFocused.focus === 'function') lastFocused.focus();
    }

    if (mainToggle) mainToggle.addEventListener('click', () => (isOpen() ? close() : open()));

    // Any "Contact Us" style button can open the popup (its href stays as a no-JS fallback).
    $$('[data-open-social]').forEach((el) => {
      el.addEventListener('click', (e) => { e.preventDefault(); open(); });
    });

    $$('[data-close-social]', popup).forEach((el) => el.addEventListener('click', close));

    document.addEventListener('keydown', (e) => {
      if (!isOpen()) return;
      if (e.key === 'Escape') { e.preventDefault(); close(); }
      else trapFocus(e, card);
    });
  }


  /* ------------------------------------------------------------------------
     9. GALLERY CATEGORY FILTER  (events.html)
     Buttons:  <button class="filter-btn" data-filter="weddings">
     Items:    <figure class="gallery-item" data-category="weddings">
     ------------------------------------------------------------------------ */
  function initGalleryFilter() {
    const buttons = $$('.filter-btn');
    if (!buttons.length || !$$('.gallery-item').length) return;

    const status = $('#gallery-count');
    const labels = {};
    buttons.forEach((b) => { labels[b.getAttribute('data-filter')] = b.textContent.trim(); });

    let activeFilter = 'all';

    function applyFilter(category, animate = true) {
      activeFilter = category;
      // Read the items every time: the admin panel can add more (section 11).
      const items = $$('.gallery-item');
      let shown = 0;

      items.forEach((item) => {
        const match = category === 'all' || item.getAttribute('data-category') === category;
        item.hidden = !match;
        item.classList.remove('is-entering');
        if (match) {
          shown += 1;
          if (animate) {
            void item.offsetWidth;               // restart the entrance animation
            item.classList.add('is-entering');
          }
        }
      });

      buttons.forEach((b) => b.setAttribute('aria-pressed', String(b.getAttribute('data-filter') === category)));

      if (status) {
        const noun = shown === 1 ? 'item' : 'items';
        status.textContent = category === 'all'
          ? 'Showing all ' + shown + ' ' + noun
          : 'Showing ' + shown + ' ' + labels[category].toLowerCase() + ' ' + noun;
      }
    }

    buttons.forEach((b) => b.addEventListener('click', () => applyFilter(b.getAttribute('data-filter'))));

    // Used by section 11 after new items arrive from the API.
    refreshGalleryFilter = () => applyFilter(activeFilter);

    // The markup ships a fixed counter ("Showing all 11 items") that only ever
    // changed when a filter was clicked. Count what is really on the page – but
    // without replaying the entrance animation for every tile at load.
    applyFilter(activeFilter, false);
  }


  /* ------------------------------------------------------------------------
     10. LIGHTBOX  (events.html)
     The whole viewer is created here – nothing for it exists in the HTML.
     It works on the *currently visible* items, so it respects the filter, and
     it handles both media types:
       photos – <img class="lightbox__img">, source from data-full or the thumbnail
       films  – <video class="lightbox__video">, source from data-video on the button
     Controls: click, Enter/Space, arrow keys, swipe, Esc. The film's own
     controls keep the arrow keys while a clip is on screen.
     ------------------------------------------------------------------------ */
  function initLightbox() {
    const gallery = $('#gallery');
    if (!gallery) return;

    let list = [];          // visible gallery buttons
    let index = 0;
    let lastFocused = null;

    // ---- build the DOM ----
    const box = document.createElement('div');
    box.className = 'lightbox';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-label', 'Event media viewer');
    box.setAttribute('aria-hidden', 'true');
    box.innerHTML =
      '<button class="lightbox__btn lightbox__close" type="button" aria-label="Close viewer">' + iconSvg('x') + '</button>' +
      '<button class="lightbox__btn lightbox__prev" type="button" aria-label="Previous item">' + iconSvg('chevron-left') + '</button>' +
      '<figure class="lightbox__figure">' +
        '<img class="lightbox__img" src="" alt="">' +
        '<video class="lightbox__video" controls playsinline preload="metadata" hidden></video>' +
        '<figcaption class="lightbox__caption">' +
          '<span class="lightbox__cat"></span>' +
          '<strong class="lightbox__title"></strong>' +
          '<span class="lightbox__count" aria-live="polite"></span>' +
        '</figcaption>' +
      '</figure>' +
      '<button class="lightbox__btn lightbox__next" type="button" aria-label="Next item">' + iconSvg('chevron-right') + '</button>';
    document.body.appendChild(box);

    const img = $('.lightbox__img', box);
    const video = $('.lightbox__video', box);
    const cat = $('.lightbox__cat', box);
    const title = $('.lightbox__title', box);
    const count = $('.lightbox__count', box);
    const prevBtn = $('.lightbox__prev', box);
    const nextBtn = $('.lightbox__next', box);
    const closeBtn = $('.lightbox__close', box);

    const isOpen = () => box.classList.contains('is-open');

    // ---- show one item: a photo, or the film when the button carries data-video ----
    function show(i) {
      index = (i + list.length) % list.length;                 // wrap around
      const btn = list[index];
      const thumb = $('img', btn);
      const film = btn.getAttribute('data-video');

      video.pause();                                           // a clip never plays on in the background

      if (film) {
        img.hidden = true;
        img.removeAttribute('src');                            // let the photo go while a film is on screen
        img.alt = '';
        video.hidden = false;
        video.poster = thumb.getAttribute('src') || '';
        video.src = film;
        video.load();
      } else {
        video.hidden = true;
        video.removeAttribute('src');
        video.removeAttribute('poster');
        img.hidden = false;
        img.classList.add('is-loading');
        img.onload = img.onerror = () => img.classList.remove('is-loading');
        img.src = btn.getAttribute('data-full') || thumb.getAttribute('src');
        img.alt = thumb.getAttribute('alt') || '';
      }

      cat.textContent = btn.getAttribute('data-category-label') || '';
      title.textContent = btn.getAttribute('data-title') || '';
      count.textContent = index + 1 + ' / ' + list.length;

      // Preload neighbouring photos so next / previous feels instant
      // (films are only fetched when they are actually opened).
      [index - 1, index + 1].forEach((n) => {
        const neighbour = list[(n + list.length) % list.length];
        if (!neighbour || neighbour.getAttribute('data-video')) return;
        new Image().src = neighbour.getAttribute('data-full') || $('img', neighbour).getAttribute('src');
      });
    }

    function open(button) {
      list = $$('.gallery-item:not([hidden]) .gallery-btn', gallery);
      const start = list.indexOf(button);
      if (start === -1) return;

      lastFocused = button;
      const single = list.length < 2;
      prevBtn.hidden = single;
      nextBtn.hidden = single;

      show(start);
      box.classList.add('is-open');
      box.setAttribute('aria-hidden', 'false');
      document.body.classList.add('no-scroll');
      window.setTimeout(() => closeBtn.focus(), 40);
    }

    function close() {
      if (!isOpen()) return;
      video.pause();                                          // stop the film when the viewer closes
      box.classList.remove('is-open');
      box.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('no-scroll');
      if (lastFocused) lastFocused.focus();
    }

    // ---- events ----
    gallery.addEventListener('click', (e) => {
      const button = e.target.closest('.gallery-btn');
      if (button) open(button);
    });

    closeBtn.addEventListener('click', close);
    prevBtn.addEventListener('click', () => show(index - 1));
    nextBtn.addEventListener('click', () => show(index + 1));

    // Click on the dark backdrop (not the photo or the buttons) closes the viewer.
    box.addEventListener('click', (e) => { if (e.target === box) close(); });

    document.addEventListener('keydown', (e) => {
      if (!isOpen()) return;
      // While a film is on screen its own controls own the arrow keys (seeking).
      if (!video.hidden && e.target === video && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) return;
      switch (e.key) {
        case 'Escape': e.preventDefault(); close(); break;
        case 'ArrowLeft': e.preventDefault(); if (list.length > 1) show(index - 1); break;
        case 'ArrowRight': e.preventDefault(); if (list.length > 1) show(index + 1); break;
        default: trapFocus(e, box);
      }
    });

    // Swipe left / right on touch screens (not across a film – the player uses that gesture).
    let touchStartX = null;
    box.addEventListener('touchstart', (e) => {
      touchStartX = e.target.closest && e.target.closest('.lightbox__video') ? null : e.changedTouches[0].clientX;
    }, { passive: true });
    box.addEventListener('touchend', (e) => {
      if (touchStartX === null || list.length < 2) return;
      const dx = e.changedTouches[0].clientX - touchStartX;
      touchStartX = null;
      if (Math.abs(dx) > 50) show(dx < 0 ? index + 1 : index - 1);
    }, { passive: true });
  }


  /* ------------------------------------------------------------------------
     11. GALLERY ITEMS FROM THE ADMIN PANEL  (events.html + Flask API)
     Photos and films uploaded through /admin live in MySQL. This asks the public
     API for the PUBLISHED ones only – anything the admin keeps to themselves is
     filtered out in SQL, so a visitor never receives it – and appends them to
     the existing grid, where the category filter (section 9), the counter and
     the lightbox (section 10) treat them like any other item.

     On a plain static host, or while the API is offline, the request simply
     fails and the page keeps the photos that came with the HTML.
     ------------------------------------------------------------------------ */
  const CATEGORY_LABELS = {
    weddings: 'Weddings',
    corporate: 'Corporate',
    birthday: 'Birthday',
    concert: 'Concert',
    engagement: 'Engagement'
  };

  /** Loading preview for the grid: a placeholder tile per expected item, shown
      only when the API has not answered within GALLERY_PREVIEW_DELAY_MS. */
  const GALLERY_PREVIEW_DELAY_MS = 250;
  const GALLERY_PREVIEW_TILE = '<figure class="gallery-placeholder" aria-hidden="true"></figure>';

  /** Titles come from the database, so they are escaped before they become markup. */
  const escapeHtml = (value) => String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

  /** One <figure> exactly like the ones in events.html, for a photo or a film. */
  function galleryItemMarkup(item) {
    const category = item.category || 'weddings';
    const label = item.category_label || CATEGORY_LABELS[category] || category;
    const title = item.title || 'Event';
    const isFilm = item.kind === 'video';
    const poster = escapeHtml(item.poster_url || item.url || '');
    const action = isFilm ? 'Play film: ' : 'View larger photo: ';

    const button =
      '<button class="gallery-btn' + (isFilm ? ' gallery-btn--video' : '') + '" type="button"' +
      ' data-title="' + escapeHtml(title) + '"' +
      ' data-category-label="' + escapeHtml(label) + '"' +
      (isFilm
        ? ' data-video="' + escapeHtml(item.url || '') + '"'
        : ' data-full="' + escapeHtml(item.url || '') + '"') +
      ' aria-label="' + escapeHtml(action + title + ' (' + label + ')') + '">' +
      '<img src="' + poster + '" alt="' + escapeHtml(title + ' – ' + label) + '"' +
      ' width="1200" height="900" loading="lazy">' +
      (isFilm
        ? '<span class="gallery-play" aria-hidden="true">' + iconSvg('play') + '</span>'
        : '<span class="gallery-zoom" aria-hidden="true">' + iconSvg('maximize') + '</span>') +
      '<span class="gallery-overlay">' +
      '<span class="gallery-chip">' + escapeHtml(label) + '</span>' +
      '<span class="gallery-title">' + escapeHtml(title) + '</span>' +
      '</span></button>';

    return '<figure class="gallery-item" data-category="' + escapeHtml(category) + '">' +
      button + '</figure>';
  }

  function initGalleryApi() {
    const gallery = $('#gallery');
    if (!gallery || !window.fetch) return;

    // Loading preview: a skeleton tile per expected item appears only if the API
    // is still thinking after GALLERY_PREVIEW_DELAY_MS, so a fast answer no
    // longer flashes placeholders that are gone before they are seen.
    let settled = false;
    const previewTimer = window.setTimeout(() => {
      if (!settled) gallery.insertAdjacentHTML('beforeend', GALLERY_PREVIEW_TILE.repeat(3));
    }, GALLERY_PREVIEW_DELAY_MS);

    function clearPreview() {
      settled = true;
      window.clearTimeout(previewTimer);
      $$('.gallery-placeholder', gallery).forEach((tile) => tile.remove());
    }

    fetch('/api/media', { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        clearPreview();
        if (!data || !Array.isArray(data.items) || !data.items.length) return;
        gallery.insertAdjacentHTML('beforeend', data.items.map(galleryItemMarkup).join(''));
        refreshGalleryFilter();                  // so the count and the open filter include them
      })
      .catch(() => {
        clearPreview();                          /* static hosting or API offline – the built-in photos are enough */
      });
  }


  /* ------------------------------------------------------------------------
     12. GOOGLE MAP PLACEHOLDER
     While the iframe src is still "YOUR_GOOGLE_MAP_EMBED_URL", show a friendly
     placeholder instead of a broken frame. Replace the src in index.html with
     the real embed URL and this block does nothing.
     ------------------------------------------------------------------------ */
  function initMapPlaceholder() {
    $$('.map-wrap').forEach((wrap) => {
      const frame = $('iframe', wrap);
      if (!frame) return;
      const src = frame.getAttribute('src') || '';
      if (!/^https?:\/\//i.test(src)) {
        frame.removeAttribute('src');            // stop the browser requesting a bogus URL
        wrap.classList.add('is-placeholder');
      }
    });
  }


  /* ------------------------------------------------------------------------
     13. FOOTER YEAR
     ------------------------------------------------------------------------ */
  function initYear() {
    $$('[data-year]').forEach((el) => { el.textContent = new Date().getFullYear(); });
  }


  /* ------------------------------------------------------------------------
     14. MOUSE FLASH EFFECTS (pointer-driven light)
     Four small effects that all answer one idea: the site reacts to the mouse
     with light. Everything here is created by JavaScript and only for visitors
     who use a mouse with a fine pointer and have NOT enabled "reduce motion",
     so touch screens and reduce-motion visitors simply get the plain page.

       14a. .cursor-glow  – soft light that follows the pointer everywhere
       14b. .spotlight    – light that follows the pointer inside each card
       14c. .click-flash  – short light burst wherever the visitor clicks
       14d. .hero__flash  – light burst in the hero, whose stage lights also
                            lean towards the pointer (--beam-* on .hero)

     Only transform / opacity / custom properties are touched, so the effects
     never cause layout work and stay cheap even on long pages.
     ------------------------------------------------------------------------ */

  /** True for a real mouse pointer without a "reduce motion" preference. */
  const canUsePointer = !reducedMotion &&
    !!(window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches);

  /** Click position in viewport coordinates. Keyboard activation (Enter/Space)
      carries no coordinates, so the middle of the element is used instead. */
  function pointerPoint(event, element) {
    if (event.clientX || event.clientY) return { x: event.clientX, y: event.clientY };
    const rect = element.getBoundingClientRect();
    return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
  }

  /** 14c helper – one short light burst at x/y, cleaned up after itself. */
  function flashAt(x, y) {
    const flash = document.createElement('span');
    flash.className = 'click-flash';
    flash.setAttribute('aria-hidden', 'true');
    flash.style.setProperty('--x', x + 'px');
    flash.style.setProperty('--y', y + 'px');
    document.body.appendChild(flash);
    const remove = () => flash.remove();
    flash.addEventListener('animationend', remove);
    window.setTimeout(remove, 1200);        // safety net if animationend never fires
  }

  /** 14a – a soft light that follows the cursor across the whole page. */
  function initCursorGlow() {
    const glow = document.createElement('div');
    glow.className = 'cursor-glow';
    glow.setAttribute('aria-hidden', 'true');
    document.body.appendChild(glow);

    let x = -700, y = -700, queued = false;

    // One paint per animation frame keeps this cheap on fast mouse moves.
    const paint = () => {
      queued = false;
      glow.style.setProperty('--x', x + 'px');
      glow.style.setProperty('--y', y + 'px');
    };

    document.addEventListener('pointermove', (e) => {
      x = e.clientX;
      y = e.clientY;
      glow.classList.add('is-visible');
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(paint);
    }, { passive: true });

    // No light while the pointer is outside the window.
    document.addEventListener('mouseleave', () => glow.classList.remove('is-visible'));
    window.addEventListener('blur', () => glow.classList.remove('is-visible'));
  }

  /** 14b – the same light, but confined to the card under the pointer. */
  function initCardSpotlight() {
    const cards = $$('.service-card, .why-card, .pillar, .team-member, .contact-card, .gallery-btn, .mission-quote, .stat');
    if (!cards.length) return;

    cards.forEach((card) => {
      card.classList.add('spotlight');

      card.addEventListener('pointermove', (e) => {
        const rect = card.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        card.style.setProperty('--spot-x', ((e.clientX - rect.left) / rect.width * 100).toFixed(2) + '%');
        card.style.setProperty('--spot-y', ((e.clientY - rect.top) / rect.height * 100).toFixed(2) + '%');
      }, { passive: true });

      // The light falls back to the middle of the card when the pointer leaves.
      card.addEventListener('pointerleave', () => {
        card.style.removeProperty('--spot-x');
        card.style.removeProperty('--spot-y');
      }, { passive: true });
    });
  }

  /** 14c – a quick flash of light wherever an interactive element is used. */
  function initClickFlash() {
    document.addEventListener('click', (e) => {
      const target = e.target.closest && e.target.closest('a, button, [role="button"]');
      if (!target) return;
      const point = pointerPoint(e, target);
      flashAt(point.x, point.y);
    });
  }

  /** 14d – hero stage lights lean towards the pointer and flash on click. */
  function initHeroBeams() {
    const hero = $('.hero');
    if (!hero) return;

    const flash = document.createElement('span');
    flash.className = 'hero__flash';
    flash.setAttribute('aria-hidden', 'true');
    hero.appendChild(flash);

    let px = .5, py = .4, queued = false;   // pointer position inside the hero (0–1)

    const paint = () => {
      queued = false;
      hero.style.setProperty('--beam-shift', ((px - .5) * 48).toFixed(1) + 'px');
      hero.style.setProperty('--beam-tilt', ((px - .5) * 3).toFixed(2) + 'deg');
      hero.style.setProperty('--beam-light', (1 + (1 - py) * .45).toFixed(2));
      flash.style.setProperty('--fx', (px * 100).toFixed(1) + '%');
      flash.style.setProperty('--fy', (py * 100).toFixed(1) + '%');
    };

    hero.addEventListener('pointermove', (e) => {
      const rect = hero.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      px = (e.clientX - rect.left) / rect.width;
      py = (e.clientY - rect.top) / rect.height;
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(paint);
    }, { passive: true });

    // Pointer gone: the lights settle back to their CSS defaults.
    hero.addEventListener('pointerleave', () => {
      ['--beam-shift', '--beam-tilt', '--beam-light'].forEach((name) => hero.style.removeProperty(name));
    }, { passive: true });

    hero.addEventListener('pointerdown', (e) => {
      const rect = hero.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      flash.style.setProperty('--fx', (((e.clientX - rect.left) / rect.width) * 100).toFixed(1) + '%');
      flash.style.setProperty('--fy', (((e.clientY - rect.top) / rect.height) * 100).toFixed(1) + '%');
      flash.classList.remove('is-flashing');
      void flash.offsetWidth;             // restart the animation on every click
      flash.classList.add('is-flashing');
    });
  }

  /** 14 – starts every pointer-driven light effect (mouse + no reduce-motion). */
  function initMouseFlash() {
    if (!canUsePointer) return;
    initCursorGlow();
    initCardSpotlight();
    initClickFlash();
    initHeroBeams();
  }


  /* ------------------------------------------------------------------------
     15. PAGE PREVIEW  (loading overlay – every page)
     The overlay in the HTML is what a visitor sees between the first paint and
     the moment the page is ready. This module only decides when it goes away:

       * as soon as the page has loaded (images included) – but never before
         PREVIEW_MIN_MS, so the brand mark does not simply flicker,
       * right away on back / forward, because the browser restores the page
         from its own cache and nothing is really loading,
       * never later than PREVIEW_MAX_MS, so one slow image cannot hold the site
         hostage,

     and it comes back whenever a link to another page of this site is followed,
     which is what makes moving between the three pages feel continuous.
     Section 23 of the stylesheet keeps the preview still for reduce-motion
     visitors instead of spinning.
     ------------------------------------------------------------------------ */
  const PREVIEW_MIN_MS = 450;
  const PREVIEW_MAX_MS = 4000;

  function initPageLoader() {
    const loader = $('#page-loader');
    if (!loader) return;

    let shownAt = Date.now();
    let hideTimer = null;

    /** Shows the preview and arms the safety net. */
    function show() {
      shownAt = Date.now();
      window.clearTimeout(hideTimer);
      hideTimer = window.setTimeout(hide, PREVIEW_MAX_MS);
      root.classList.add('page-loading');
      loader.classList.remove('is-done');
      loader.removeAttribute('aria-hidden');
    }

    /** Fades the preview away. */
    function hide() {
      window.clearTimeout(hideTimer);
      root.classList.remove('page-loading');
      loader.classList.add('is-done');
      loader.setAttribute('aria-hidden', 'true');
    }

    /** The page is ready: hold the preview for the minimum time, then hide it. */
    function hideWhenReady() {
      const wait = reducedMotion ? 0 : Math.max(0, PREVIEW_MIN_MS - (Date.now() - shownAt));
      window.clearTimeout(hideTimer);
      hideTimer = window.setTimeout(hide, wait);
    }

    show();

    if (document.readyState === 'complete') hideWhenReady();
    else window.addEventListener('load', hideWhenReady, { once: true });

    // back / forward – the page came out of the browser's cache fully formed
    window.addEventListener('pageshow', (event) => { if (event.persisted) hide(); });

    // a link to another page of this site is being followed
    document.addEventListener('click', (event) => {
      const link = event.target.closest ? event.target.closest('a[href]') : null;
      if (!link || event.defaultPrevented || event.button > 0 ||
          event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if ((link.getAttribute('target') || '_self') !== '_self' || link.hasAttribute('download')) return;

      const href = link.getAttribute('href') || '';
      if (!href || href.charAt(0) === '#' || /^(mailto|tel|javascript):/i.test(href)) return;

      const url = new URL(link.href, window.location.href);
      if (url.origin !== window.location.origin || !/\.html?$/i.test(url.pathname)) return;
      // Same page: the browser does not reload, so there is nothing to preview.
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;

      show();
    }, true);
  }


  /* ------------------------------------------------------------------------
     Start everything once the DOM is ready
     ------------------------------------------------------------------------ */
  function init() {
    initPageLoader();                        // first: this is what the visitor is looking at
    injectSprite();
    initTheme();
    initHeader();
    initActiveNav();
    initSmoothScroll();
    initBackToTop();
    initReveal();
    initCounters();
    initSocialPopup();
    initGalleryFilter();
    initLightbox();
    initGalleryApi();
    initMapPlaceholder();
    initYear();
    initMouseFlash();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
