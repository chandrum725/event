/* ==========================================================================
   EVENTORA – ADMIN PANEL BEHAVIOUR
   Vanilla JavaScript · no libraries · loaded only by templates/admin/dashboard.html

   Small conveniences on top of a form that already works without them:
     1. Confirm before deleting an item
     2. Live preview of the file the admin picked
     3. Media type follows the chosen file, and the poster box appears for films
     4. Title filled in from the file name when it is left empty
     5. "Copy link" buttons
   ========================================================================== */

(function () {
  'use strict';

  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));

  const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'avif'];
  const VIDEO_EXTENSIONS = ['mp4', 'webm', 'ogv', 'mov', 'm4v'];

  const extensionOf = (name) => {
    const parts = String(name || '').toLowerCase().split('.');
    return parts.length > 1 ? parts.pop() : '';
  };

  const kindOf = (name) => {
    const ext = extensionOf(name);
    if (VIDEO_EXTENSIONS.indexOf(ext) !== -1) return 'video';
    if (IMAGE_EXTENSIONS.indexOf(ext) !== -1) return 'image';
    return null;
  };

  /* ------------------------------------------------------------------------
     1. CONFIRM BEFORE DELETING
     Any <form data-confirm="..."> asks first – the message comes from the
     template, so it can name the item.
     ------------------------------------------------------------------------ */
  function initDeleteConfirmation() {
    $$('form[data-confirm]').forEach((form) => {
      form.addEventListener('submit', (event) => {
        if (!window.confirm(form.getAttribute('data-confirm'))) event.preventDefault();
      });
    });
  }

  /* ------------------------------------------------------------------------
     5. COPY A MEDIA LINK
     ------------------------------------------------------------------------ */
  function initCopyButtons() {
    if (!navigator.clipboard) return;

    $$('.js-copy').forEach((button) => {
      const original = button.textContent;

      button.addEventListener('click', () => {
        navigator.clipboard.writeText(button.getAttribute('data-copy') || '').then(() => {
          button.textContent = 'Link copied';
          window.setTimeout(() => { button.textContent = original; }, 1600);
        }).catch(() => { /* clipboard blocked – the URL is visible in the field above */ });
      });
    });
  }

  /* ------------------------------------------------------------------------
     2–4. THE UPLOAD FORM
     ------------------------------------------------------------------------ */
  function initUploadForm() {
    const form = $('[data-upload-form]');
    if (!form) return;

    const fileInput = $('[data-file-input]', form);
    const kindSelect = $('[data-kind-select]', form);
    const titleInput = $('[data-title-input]', form);
    const posterField = $('[data-poster-field]', form);
    const preview = $('[data-preview]', form);
    let previewUrl = null;

    const showPosterField = (kind) => {
      if (!posterField) return;
      posterField.hidden = kind !== 'video';
    };

    const clearPreview = () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        previewUrl = null;
      }
      if (preview) {
        preview.hidden = true;
        preview.innerHTML = '';
      }
    };

    const renderPreview = (file, kind) => {
      if (!preview || !file) return;
      clearPreview();

      previewUrl = URL.createObjectURL(file);
      preview.hidden = false;
      preview.innerHTML =
        (kind === 'video'
          ? '<video controls muted playsinline preload="metadata" src="' + previewUrl + '"></video>'
          : '<img src="' + previewUrl + '" alt="">') +
        '<p class="admin-preview__name"></p>';
      $('.admin-preview__name', preview).textContent =
        file.name + ' · ' + (file.size / (1024 * 1024)).toFixed(1) + ' MB – nothing is sent until you press Upload.';
    };

    if (fileInput) {
      fileInput.addEventListener('change', () => {
        const file = fileInput.files && fileInput.files[0];
        if (!file) {
          clearPreview();
          return;
        }

        const kind = kindOf(file.name);
        if (kind && kindSelect) {
          kindSelect.value = kind;                 // the file decides, not the dropdown
          showPosterField(kind);
        }
        // A helpful default title: "royal-palace-wedding.mp4" -> "Royal Palace Wedding"
        if (titleInput && !titleInput.value.trim()) {
          const stem = file.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').trim();
          if (stem) titleInput.value = stem.replace(/\b\w/g, (c) => c.toUpperCase()).slice(0, 160);
        }
        renderPreview(file, kind || (kindSelect && kindSelect.value));
      });
    }

    if (kindSelect) {
      kindSelect.addEventListener('change', () => showPosterField(kindSelect.value));
      showPosterField(kindSelect.value);

      // Uploading a .mp4 while "image" is selected would be refused – say it now.
      form.addEventListener('submit', (event) => {
        const file = fileInput && fileInput.files && fileInput.files[0];
        if (!file) return;
        const kind = kindOf(file.name);
        if (kind && kindSelect.value !== kind) {
          kindSelect.value = kind;
        }
      });
    }

    window.addEventListener('beforeunload', clearPreview);
  }

  /* ------------------------------------------------------------------------
     Start
     ------------------------------------------------------------------------ */
  function init() {
    initDeleteConfirmation();
    initCopyButtons();
    initUploadForm();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
