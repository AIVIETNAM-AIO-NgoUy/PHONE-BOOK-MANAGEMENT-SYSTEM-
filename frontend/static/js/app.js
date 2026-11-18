/* ==========================================================================
   Phone Book Management System — Core Vanilla JS Helpers
   - HTMX CSRF header injector
   - Modal confirmation dialog handler
   - Dismissible alert toast close handler
   - Responsive left sidebar drawer toggle
   ========================================================================== */

(function () {
  "use strict";

  /**
   * Retrieve CSRF token from <meta name="csrf-token"> or the csrftoken cookie.
   */
  function getCsrfToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag && metaTag.content && metaTag.content !== "NOTPROVIDED") {
      return metaTag.content;
    }

    const cookieMatch = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrftoken="));

    return cookieMatch ? decodeURIComponent(cookieMatch.split("=")[1]) : "";
  }

  /**
   * Inject X-CSRFToken header into every HTMX request automatically.
   */
  document.addEventListener("htmx:configRequest", function (event) {
    const token = getCsrfToken();
    if (token) {
      event.detail.headers["X-CSRFToken"] = token;
    }
  });

  /**
   * Dismissible alert toast handler.
   */
  function dismissAlert(alertEl) {
    if (!alertEl) {
      return;
    }
    alertEl.classList.add("is-dismissing");
    window.setTimeout(function () {
      if (alertEl.parentNode) {
        alertEl.parentNode.removeChild(alertEl);
      }
    }, 150);
  }

  document.addEventListener("click", function (event) {
    const dismissBtn = event.target.closest("[data-dismiss-alert]");
    if (dismissBtn) {
      const alertEl = dismissBtn.closest("[data-alert]");
      dismissAlert(alertEl);
    }
  });

  /**
   * Auto-dismiss alerts inside guest toast containers (.toast-container-guest).
   * Automatically calls dismissAlert(alertEl) after 5000ms (5 seconds).
   * Pauses when hovered (mouseenter) and resumes on mouseleave.
   */
  function setupAlertAutoDismiss(alertEl, duration) {
    if (!alertEl || alertEl.dataset.autoDismissInitialized === "true") {
      return;
    }
    alertEl.dataset.autoDismissInitialized = "true";
    const timeoutDuration = typeof duration === "number" ? duration : 5000;

    let remaining = timeoutDuration;
    let startTime = Date.now();
    let timerId = null;

    function startTimer() {
      startTime = Date.now();
      timerId = window.setTimeout(function () {
        dismissAlert(alertEl);
      }, remaining);
    }

    function pauseTimer() {
      if (timerId !== null) {
        window.clearTimeout(timerId);
        timerId = null;
        remaining -= Date.now() - startTime;
      }
    }

    alertEl.addEventListener("mouseenter", pauseTimer);
    alertEl.addEventListener("mouseleave", function () {
      if (remaining > 0) {
        startTimer();
      } else {
        dismissAlert(alertEl);
      }
    });

    startTimer();
  }

  function initGuestAlerts(root) {
    const scope = root && root.querySelectorAll ? root : document;
    const alerts = scope.querySelectorAll(".toast-container-guest [data-alert]");
    alerts.forEach(function (alertEl) {
      setupAlertAutoDismiss(alertEl, 5000);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initGuestAlerts();
    });
  } else {
    initGuestAlerts();
  }

  document.addEventListener("htmx:load", function (event) {
    const target = event.detail ? event.detail.elt : document;
    if (target && target.querySelectorAll) {
      initGuestAlerts(target);
    }
  });

  /**
   * Responsive Left Sidebar Drawer Handler (<= 900px).
   */
  const sidebarToggle = document.querySelector("[data-sidebar-toggle]");
  const sidebarEl = document.querySelector("[data-app-sidebar]");
  const sidebarBackdrop = document.querySelector("[data-sidebar-backdrop]");

  function openSidebar() {
    if (!sidebarEl || !sidebarToggle) {
      return;
    }
    sidebarEl.classList.add("is-open");
    if (sidebarBackdrop) {
      sidebarBackdrop.classList.add("is-open");
    }
    sidebarToggle.setAttribute("aria-expanded", "true");
    document.body.classList.add("sidebar-drawer-open");
  }

  function closeSidebar() {
    if (!sidebarEl || !sidebarToggle) {
      return;
    }
    if (!sidebarEl.classList.contains("is-open")) {
      return;
    }
    sidebarEl.classList.remove("is-open");
    if (sidebarBackdrop) {
      sidebarBackdrop.classList.remove("is-open");
    }
    sidebarToggle.setAttribute("aria-expanded", "false");
    document.body.classList.remove("sidebar-drawer-open");
  }

  if (sidebarToggle && sidebarEl) {
    sidebarToggle.addEventListener("click", function () {
      if (sidebarEl.classList.contains("is-open")) {
        closeSidebar();
      } else {
        openSidebar();
      }
    });
  }

  if (sidebarBackdrop) {
    sidebarBackdrop.addEventListener("click", function () {
      closeSidebar();
    });
  }

  if (sidebarEl) {
    sidebarEl.addEventListener("click", function (event) {
      if (event.target.closest(".sidebar-link")) {
        closeSidebar();
      }
    });
  }

  if (typeof window.matchMedia === "function") {
    const desktopMediaQuery = window.matchMedia("(min-width: 901px)");
    const handleViewportChange = function (e) {
      if (e.matches) {
        closeSidebar();
      }
    };
    if (typeof desktopMediaQuery.addEventListener === "function") {
      desktopMediaQuery.addEventListener("change", handleViewportChange);
    }
  }

  /**
   * Global Confirmation Modal Handler.
   * Supports triggers with `data-confirm-modal` attribute:
   *   data-confirm-title="Delete Contact"
   *   data-confirm-message="This action cannot be undone."
   *   data-confirm-url="/contacts/1/delete/"
   *   data-confirm-label="Delete"
   */
  const modalBackdrop = document.getElementById("confirm-modal-backdrop");
  const modalTitle = document.getElementById("confirm-modal-title");
  const modalMessage = document.getElementById("confirm-modal-message");
  const modalForm = document.getElementById("confirm-modal-form");
  const modalConfirmBtn = document.getElementById("confirm-modal-submit");
  const modalCancelBtns = document.querySelectorAll("[data-modal-close]");

  let lastFocusedElement = null;
  let pendingCallback = null;

  function openConfirmModal(options) {
    if (!modalBackdrop) {
      return;
    }

    lastFocusedElement = document.activeElement;
    if (modalTitle) {
      modalTitle.textContent = options.title || "Confirm Action";
    }
    if (modalMessage) {
      modalMessage.textContent = options.message || "Are you sure you want to proceed?";
    }
    if (modalConfirmBtn) {
      modalConfirmBtn.textContent = options.confirmLabel || "Confirm";
    }
    if (modalForm && options.url) {
      modalForm.setAttribute("action", options.url);
    }

    pendingCallback = typeof options.onConfirm === "function" ? options.onConfirm : null;

    modalBackdrop.classList.add("is-open");
    modalBackdrop.setAttribute("aria-hidden", "false");

    if (modalConfirmBtn) {
      modalConfirmBtn.focus();
    }
  }

  function closeConfirmModal() {
    if (!modalBackdrop || !modalBackdrop.classList.contains("is-open")) {
      return;
    }

    modalBackdrop.classList.remove("is-open");
    modalBackdrop.setAttribute("aria-hidden", "true");
    pendingCallback = null;

    if (lastFocusedElement && typeof lastFocusedElement.focus === "function") {
      lastFocusedElement.focus();
      lastFocusedElement = null;
    }
  }

  document.addEventListener("click", function (event) {
    const trigger = event.target.closest("[data-confirm-modal]");
    if (!trigger) {
      return;
    }

    event.preventDefault();
    const targetForm = trigger.closest("form");
    const actionUrl = trigger.getAttribute("data-confirm-url") || (targetForm ? targetForm.action : "");

    openConfirmModal({
      title: trigger.getAttribute("data-confirm-title") || "Confirm Action",
      message: trigger.getAttribute("data-confirm-message") || "Are you sure you want to proceed?",
      confirmLabel: trigger.getAttribute("data-confirm-label") || "Confirm",
      url: actionUrl,
      onConfirm:
        targetForm && !trigger.getAttribute("data-confirm-url")
          ? function () {
              targetForm.submit();
            }
          : null,
    });
  });

  if (modalForm) {
    modalForm.addEventListener("submit", function (event) {
      if (pendingCallback) {
        event.preventDefault();
        const callback = pendingCallback;
        closeConfirmModal();
        callback();
      }
    });
  }

  modalCancelBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      closeConfirmModal();
    });
  });

  if (modalBackdrop) {
    modalBackdrop.addEventListener("click", function (event) {
      if (event.target === modalBackdrop) {
        closeConfirmModal();
      }
    });
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeConfirmModal();
      closeSidebar();
    }
  });

  /**
   * Interaction frequency logger (POST /contacts/<id>/interact/).
   */
  document.addEventListener("click", function (event) {
    const interactBtn = event.target.closest("[data-log-interaction]");
    if (!interactBtn) {
      return;
    }

    const url = interactBtn.getAttribute("data-interact-url");
    const contactId = interactBtn.getAttribute("data-contact-id");
    if (!url || interactBtn.disabled) {
      return;
    }

    interactBtn.disabled = true;
    fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": getCsrfToken(),
        Accept: "application/json",
      },
      credentials: "same-origin",
    })
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error("Failed to record interaction");
        }
        return resp.json();
      })
      .then(function (payload) {
        if (contactId && typeof payload.interaction_count !== "undefined") {
          document
            .querySelectorAll('[data-interaction-count="' + contactId + '"]')
            .forEach(function (el) {
              el.textContent = String(payload.interaction_count);
            });
          document
            .querySelectorAll('[data-last-contacted="' + contactId + '"]')
            .forEach(function (el) {
              el.textContent = "Just now";
            });
        }
      })
      .catch(function () {
        // Silently restore button state on transient error
      })
      .finally(function () {
        interactBtn.disabled = false;
      });
  });

  /**
   * Sliding Auth Card Switcher (Login <-> Register) with History & Accessibility Sync.
   */
  function initAuthCardSwitcher() {
    const authCard = document.querySelector("[data-auth-card]");
    if (!authCard) {
      return;
    }

    const loginPanel = authCard.querySelector('[data-auth-panel="login"]');
    const registerPanel = authCard.querySelector('[data-auth-panel="register"]');
    const loginBanner = authCard.querySelector('[data-auth-banner="login"]');
    const registerBanner = authCard.querySelector('[data-auth-banner="register"]');
    const switchLinks = authCard.querySelectorAll("[data-auth-switch]");
    let animTimerId = null;

    function clearTransitionClasses() {
      if (animTimerId !== null) {
        window.clearTimeout(animTimerId);
        animTimerId = null;
      }
      authCard.classList.remove("is-animating-register", "is-animating-login");
    }

    function setInactiveState(el, isInactive) {
      if (!el) {
        return;
      }
      el.setAttribute("aria-hidden", isInactive ? "true" : "false");
      if ("inert" in el) {
        el.inert = isInactive;
      } else if (isInactive) {
        el.setAttribute("inert", "");
      } else {
        el.removeAttribute("inert");
      }
    }

    function syncAccessibility(mode) {
      const isRegister = mode === "register";
      setInactiveState(loginPanel, isRegister);
      setInactiveState(registerPanel, !isRegister);
      setInactiveState(loginBanner, isRegister);
      setInactiveState(registerBanner, !isRegister);
      authCard.setAttribute("data-auth-mode", mode);
    }

    function focusActiveForm(mode) {
      const targetPanel = mode === "register" ? registerPanel : loginPanel;
      if (!targetPanel) {
        return;
      }
      const firstInput = targetPanel.querySelector(
        'input:not([type="hidden"]):not([disabled])'
      );
      if (firstInput && typeof firstInput.focus === "function") {
        window.setTimeout(function () {
          firstInput.focus({ preventScroll: true });
        }, 360);
      }
    }

    function setAuthMode(mode, options) {
      const normalizedMode = mode === "register" ? "register" : "login";
      const isRegister = normalizedMode === "register";
      const currentlyRegister = authCard.classList.contains("is-register");

      if (isRegister !== currentlyRegister) {
        clearTransitionClasses();
        void authCard.offsetWidth;
        authCard.classList.add(isRegister ? "is-animating-register" : "is-animating-login");
        authCard.classList.toggle("is-register", isRegister);
        animTimerId = window.setTimeout(function () {
          authCard.classList.remove("is-animating-register", "is-animating-login");
          animTimerId = null;
        }, 700);
      }

      syncAccessibility(normalizedMode);
      document.title = isRegister
        ? "Register — Phone Book Management System"
        : "Sign In — Phone Book Management System";

      if (options && options.pushUrl && typeof window.history.pushState === "function") {
        try {
          const targetUrl = new URL(options.pushUrl, window.location.origin);
          if (targetUrl.pathname !== window.location.pathname) {
            window.history.pushState({ authMode: normalizedMode }, "", targetUrl.href);
          }
        } catch (_err) {
          // Ignore malformed URLs and keep UI state intact
        }
      }

      if (options && options.focusInput) {
        focusActiveForm(normalizedMode);
      }
    }

    const initialMode = authCard.classList.contains("is-register") ? "register" : "login";
    syncAccessibility(initialMode);
    if (typeof window.history.replaceState === "function") {
      window.history.replaceState({ authMode: initialMode }, "", window.location.href);
    }

    switchLinks.forEach(function (link) {
      link.addEventListener("click", function (event) {
        const targetMode = link.getAttribute("data-auth-switch");
        if (targetMode !== "register" && targetMode !== "login") {
          return;
        }
        event.preventDefault();
        setAuthMode(targetMode, {
          pushUrl: link.href,
          focusInput: true,
        });
      });
    });

    window.addEventListener("popstate", function (event) {
      const stateMode = event.state && event.state.authMode;
      const inferredMode =
        stateMode ||
        (window.location.pathname.indexOf("register") !== -1 ? "register" : "login");
      setAuthMode(inferredMode, { focusInput: false });
    });
  }

  initAuthCardSwitcher();

  /**
   * Action Dropdown Menus (.dropdown / [data-dropdown-toggle])
   */
  function initActionDropdowns() {
    function closeAllDropdowns() {
      document.querySelectorAll(".dropdown.is-open").forEach(function (dd) {
        dd.classList.remove("is-open");
        const toggle = dd.querySelector("[data-dropdown-toggle]");
        if (toggle) {
          toggle.setAttribute("aria-expanded", "false");
        }
      });
    }

    document.addEventListener("click", function (event) {
      const toggle = event.target.closest("[data-dropdown-toggle]");
      if (toggle) {
        event.preventDefault();
        event.stopPropagation();
        const dropdown = toggle.closest(".dropdown");
        if (!dropdown) {
          return;
        }
        const willOpen = !dropdown.classList.contains("is-open");
        closeAllDropdowns();
        if (willOpen) {
          dropdown.classList.add("is-open");
          toggle.setAttribute("aria-expanded", "true");
        }
        return;
      }

      const openDropdown = event.target.closest(".dropdown.is-open");
      if (openDropdown) {
        if (event.target.closest(".dropdown-item")) {
          closeAllDropdowns();
        }
        return;
      }

      closeAllDropdowns();
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeAllDropdowns();
      }
    });
  }

  initActionDropdowns();

  /**
   * Global Admin Modals & Action Triggers
   */
  function initAdminModals() {
    let lastAdminFocusedEl = null;

    function openModal(modalId, triggerEl) {
      const modal = document.getElementById(modalId);
      if (!modal) {
        return;
      }
      lastAdminFocusedEl = triggerEl || document.activeElement;
      modal.classList.add("is-open");
      modal.setAttribute("aria-hidden", "false");

      const focusTarget = modal.querySelector(
        "input:not([type='hidden']), button[type='submit']"
      );
      if (focusTarget && typeof focusTarget.focus === "function") {
        focusTarget.focus();
      }
    }

    function closeModal(modal) {
      if (!modal || !modal.classList.contains("is-open")) {
        return;
      }
      modal.classList.remove("is-open");
      modal.setAttribute("aria-hidden", "true");

      const reasonInput = modal.querySelector("#lock-reason-input, #table-lock-reason");
      if (reasonInput) {
        reasonInput.value = "";
      }

      if (lastAdminFocusedEl && typeof lastAdminFocusedEl.focus === "function") {
        lastAdminFocusedEl.focus();
        lastAdminFocusedEl = null;
      }
    }

    function closeAllOpenModals() {
      document
        .querySelectorAll(".modal-backdrop.is-open:not(#confirm-modal-backdrop)")
        .forEach(function (m) {
          closeModal(m);
        });
    }

    document.addEventListener("click", function (event) {
      const openBtn = event.target.closest("[data-admin-modal-open]");
      if (openBtn) {
        event.preventDefault();
        openModal(openBtn.getAttribute("data-admin-modal-open"), openBtn);
        return;
      }

      const lockBtn = event.target.closest("[data-action-lock]");
      if (lockBtn) {
        event.preventDefault();
        const modal = document.getElementById("table-lock-modal");
        const form = document.getElementById("table-lock-form");
        const usernameEl = document.getElementById("table-lock-username");
        if (modal && form) {
          form.setAttribute("action", lockBtn.getAttribute("data-lock-url"));
          if (usernameEl) {
            usernameEl.textContent = lockBtn.getAttribute("data-username");
          }
          openModal("table-lock-modal", lockBtn);
        }
        return;
      }

      const unlockBtn = event.target.closest("[data-action-unlock]");
      if (unlockBtn) {
        event.preventDefault();
        const modal = document.getElementById("table-unlock-modal");
        const form = document.getElementById("table-unlock-form");
        const usernameEl = document.getElementById("table-unlock-username");
        if (modal && form) {
          form.setAttribute("action", unlockBtn.getAttribute("data-unlock-url"));
          if (usernameEl) {
            usernameEl.textContent = unlockBtn.getAttribute("data-username");
          }
          openModal("table-unlock-modal", unlockBtn);
        }
        return;
      }

      const closeBtn = event.target.closest("[data-admin-modal-close]");
      if (closeBtn) {
        event.preventDefault();
        const modalId = closeBtn.getAttribute("data-admin-modal-close");
        closeModal(
          modalId
            ? document.getElementById(modalId)
            : closeBtn.closest(".modal-backdrop")
        );
        return;
      }

      if (
        event.target.classList &&
        event.target.classList.contains("modal-backdrop") &&
        event.target.id !== "confirm-modal-backdrop"
      ) {
        closeModal(event.target);
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeAllOpenModals();
      }
    });
  }

  initAdminModals();

  /**
   * Update favorites counter badge when an item is removed via HTMX.
   */
  document.body.addEventListener("favoriteRemoved", function () {
    const badge = document.getElementById("favorites-count-badge");
    if (badge) {
      const current = parseInt(badge.textContent || "0", 10);
      if (!Number.isNaN(current) && current > 0) {
        badge.textContent = String(current - 1);
      }
    }
  });

  window.PhoneBookUI = {
    getCsrfToken: getCsrfToken,
    openConfirmModal: openConfirmModal,
    closeConfirmModal: closeConfirmModal,
    dismissAlert: dismissAlert,
    setupAlertAutoDismiss: setupAlertAutoDismiss,
    initGuestAlerts: initGuestAlerts,
    openSidebar: openSidebar,
    closeSidebar: closeSidebar,
  };
})();
