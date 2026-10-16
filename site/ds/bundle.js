/* @ds-bundle: {"format":4,"namespace":"RJ","components":[{"name":"Button"},{"name":"Tag"},{"name":"FilterChips"},{"name":"MediaFrame"},{"name":"ProjectCard"},{"name":"HeroCarousel"},{"name":"LineReveal"},{"name":"Reveal"},{"name":"SiteHeader"},{"name":"LinkPanel"}]} */
(function () {
  "use strict";
  var React = window.React;
  var h = React.createElement;
  var useState = React.useState, useEffect = React.useEffect, useRef = React.useRef,
    useCallback = React.useCallback, useLayoutEffect = React.useLayoutEffect;

  /* ---------- shared ---------- */

  function cx() {
    var out = [];
    for (var i = 0; i < arguments.length; i++) if (arguments[i]) out.push(arguments[i]);
    return out.join(" ");
  }

  function omit(obj, keys) {
    var out = {};
    for (var k in obj) if (Object.prototype.hasOwnProperty.call(obj, k) && keys.indexOf(k) < 0) out[k] = obj[k];
    return out;
  }

  var REDUCE = "(prefers-reduced-motion: reduce)";
  function prefersReduced() {
    return typeof window.matchMedia === "function" && window.matchMedia(REDUCE).matches;
  }
  function useReducedMotion() {
    var s = useState(prefersReduced), reduced = s[0], set = s[1];
    useEffect(function () {
      if (typeof window.matchMedia !== "function") return;
      var mq = window.matchMedia(REDUCE);
      var on = function () { set(mq.matches); };
      if (mq.addEventListener) mq.addEventListener("change", on); else mq.addListener(on);
      return function () { if (mq.removeEventListener) mq.removeEventListener("change", on); else mq.removeListener(on); };
    }, []);
    return reduced;
  }

  /* Reads a duration token (e.g. --duration-dwell: 6000ms) from the page, in ms. */
  function tokenMs(name, fallback) {
    try {
      var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      if (!v) return fallback;
      var n = parseFloat(v);
      if (isNaN(n)) return fallback;
      return /ms$/.test(v) ? n : n * 1000;
    } catch (e) { return fallback; }
  }

  /* True once the element's top has come 15% of the viewport into view (and stays true). */
  function useInView(ref, enabled) {
    var s = useState(false), seen = s[0], set = s[1];
    useEffect(function () {
      if (!enabled || seen) return;
      var el = ref.current;
      if (!el || typeof IntersectionObserver !== "function") { set(true); return; }
      var io = new IntersectionObserver(function (entries) {
        for (var i = 0; i < entries.length; i++) if (entries[i].isIntersecting) { set(true); io.disconnect(); return; }
      }, { threshold: 0, rootMargin: "0px 0px -15% 0px" });
      io.observe(el);
      return function () { io.disconnect(); };
    }, [enabled, seen]);
    return seen;
  }

  function isKeyboardFocus(el) {
    try { return el.matches(":focus-visible"); } catch (e) { return true; }
  }

  var ICONS = {
    "arrow-right": "M5 12h14|m12 5 7 7-7 7",
    "arrow-up-right": "M7 7h10v10|M7 17 17 7",
    "chevron-left": "m15 18-6-6 6-6",
    "chevron-right": "m9 18 6-6-6-6",
    "chevron-down": "m6 9 6 6 6-6",
    "play": "M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z",
    "plus": "M5 12h14|M12 5v14",
    "x": "M18 6 6 18|m6 6 12 12",
    "check": "M20 6 9 17l-5-5",
    "search": "m21 21-4.34-4.34|M11 3a8 8 0 1 0 0 16 8 8 0 0 0 0-16z",
    "external-link": "M15 3h6v6|M10 14 21 3|M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6",
    "menu": "M4 5h16|M4 12h16|M4 19h16",
    "chart-line": "M3 3v16a2 2 0 0 0 2 2h16|m19 9-5 5-4-4-3 3"
  };
  function Icon(props) {
    var size = props.size || 20;
    if (props.name === "pause") {
      return h("svg", { className: cx("rj-icon", props.className), width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.75, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": "true", focusable: "false" },
        h("rect", { x: 14, y: 3, width: 5, height: 18, rx: 1 }), h("rect", { x: 5, y: 3, width: 5, height: 18, rx: 1 }));
    }
    var d = (ICONS[props.name] || "").split("|");
    return h("svg", { className: cx("rj-icon", props.className), width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.75, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": "true", focusable: "false" },
      d.map(function (p, i) { return h("path", { key: i, d: p }); }));
  }

  /* ---------- Button ---------- */

  function Button(props) {
    var variant = props.variant || "secondary";
    var size = props.size || "md";
    var rest = omit(props, ["variant", "size", "icon", "className", "children", "href", "disabled", "type"]);
    var cls = cx("rj-btn", "rj-btn--" + variant, "rj-btn--" + size, props.icon && "rj-btn--has-icon", props.className);
    var kids = [h("span", { key: "l", className: "rj-btn__label" }, props.children)];
    if (props.icon) kids.push(h("span", { key: "i", className: "rj-btn__icon rj-btn__icon--" + props.icon }, h(Icon, { name: props.icon, size: 20 })));
    if (props.href) {
      var a = Object.assign({}, rest, { className: cls, href: props.disabled ? undefined : props.href });
      if (props.disabled) { a["aria-disabled"] = "true"; a.tabIndex = -1; }
      return h("a", a, kids);
    }
    return h("button", Object.assign({}, rest, { className: cls, type: props.type || "button", disabled: props.disabled }), kids);
  }

  /* ---------- Tag ---------- */

  function Tag(props) {
    var tone = props.tone || "neutral";
    return h("span", { className: cx("rj-tag", "rj-tag--" + tone, props.className) },
      tone !== "neutral" ? h("span", { className: "rj-tag__dot", "aria-hidden": "true" }) : null,
      props.icon ? h(Icon, { name: props.icon, size: 16 }) : null,
      h("span", null, props.children));
  }

  /* ---------- FilterChips ---------- */

  function normOptions(options) {
    return (options || []).map(function (o) { return typeof o === "string" ? { value: o, label: o } : o; });
  }

  function FilterChips(props) {
    var options = normOptions(props.options);
    var controlled = props.value !== undefined;
    var s = useState(props.defaultValue !== undefined ? props.defaultValue : (options[0] && options[0].value));
    var value = controlled ? props.value : s[0];
    var trackRef = useRef(null);
    var indRef = useRef(null);
    var ready = useRef(false);

    var place = useCallback(function () {
      var track = trackRef.current, ind = indRef.current;
      if (!track || !ind) return;
      var btn = track.querySelector('[data-value="' + String(value).replace(/"/g, '\\"') + '"]');
      if (!btn) { ind.style.opacity = "0"; return; }
      ind.style.opacity = "1";
      ind.style.width = btn.offsetWidth + "px";
      ind.style.transform = "translateX(" + btn.offsetLeft + "px)";
      if (!ready.current) {
        requestAnimationFrame(function () { if (indRef.current) indRef.current.classList.add("is-ready"); });
        ready.current = true;
      }
    }, [value]);

    useLayoutEffect(function () { place(); }, [place, options.length]);
    useEffect(function () {
      var on = function () { place(); };
      window.addEventListener("resize", on);
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(on);
      return function () { window.removeEventListener("resize", on); };
    }, [place]);

    function choose(v) {
      if (!controlled) s[1](v);
      if (props.onChange) props.onChange(v);
    }

    return h("div", { className: cx("rj-chips", props.className), role: "group", "aria-label": props.label || "Filter" },
      h("div", { className: "rj-chips__track", ref: trackRef },
        h("span", { className: "rj-chips__indicator", ref: indRef, "aria-hidden": "true" }),
        options.map(function (o) {
          var on = o.value === value;
          return h("button", {
            key: o.value, type: "button", className: cx("rj-chip", on && "is-active"),
            "aria-pressed": on ? "true" : "false", "data-value": o.value,
            onClick: function () { choose(o.value); }
          }, o.label, o.count !== undefined ? h("span", { className: "rj-chip__count" }, o.count) : null);
        })));
  }

  /* ---------- MediaFrame ---------- */

  var sheenSeq = 0;

  function MediaFrame(props) {
    var drift = useRef(null);
    if (drift.current === null) drift.current = -((sheenSeq++ * 3700) % 12000);
    var reduced = useReducedMotion();
    var ratio = props.ratio || "16/10";
    var radius = props.radius || "lg";
    var field = props.field || "prussian";
    var videoRef = useRef(null);
    var frameRef = useRef(null);
    var ps = useState(false), userPlaying = ps[0], setUserPlaying = ps[1];
    var autoplay = !!props.src && !reduced && props.autoPlay !== false;

    useEffect(function () {
      var v = videoRef.current;
      if (v && !autoplay && !userPlaying) v.pause();
    }, [autoplay]);

    useEffect(function () {
      var v = videoRef.current, el = frameRef.current;
      if (!v || !el || !autoplay || typeof IntersectionObserver !== "function") return;
      var io = new IntersectionObserver(function (entries) {
        var e = entries[0];
        if (e.intersectionRatio >= 0.1) { var p = v.play(); if (p && p.catch) p.catch(function () {}); }
        else v.pause();
      }, { threshold: [0, 0.1] });
      io.observe(el);
      return function () { io.disconnect(); };
    }, [autoplay]);

    var media;
    if (props.src) {
      media = h("video", {
        ref: videoRef, className: "rj-media__el", src: props.src, poster: props.poster,
        muted: true, loop: true, playsInline: true, autoPlay: autoplay, preload: autoplay ? "auto" : "metadata",
        "aria-label": props.alt, tabIndex: -1
      });
    } else if (props.image) {
      media = h("img", { className: "rj-media__el", src: props.image, alt: props.alt || "", loading: props.loading || "lazy", decoding: "async" });
    } else {
      media = h("div", { className: cx("rj-media__field", "rj-field--" + field), role: props.alt ? "img" : undefined, "aria-label": props.alt },
        props.mark ? h("span", { className: "rj-media__mark", "aria-hidden": "true" }, props.mark) : null,
        h("span", { className: "rj-media__sheen", "aria-hidden": "true", style: { animationDelay: drift.current + "ms" } }));
    }

    var playBtn = null;
    if (props.src && !autoplay) {
      playBtn = h("button", {
        type: "button", className: "rj-media__play",
        "aria-label": userPlaying ? "Pause video" : "Play video",
        onClick: function (e) {
          e.preventDefault(); e.stopPropagation();
          var v = videoRef.current; if (!v) return;
          if (v.paused) { var p = v.play(); if (p && p.catch) p.catch(function () {}); setUserPlaying(true); }
          else { v.pause(); setUserPlaying(false); }
        }
      }, h(Icon, { name: userPlaying ? "pause" : "play", size: 20 }));
    }

    return h("div", {
      ref: frameRef,
      className: cx("rj-media", "rj-media--r-" + radius, props.fill && "rj-media--fill", props.className),
      style: props.fill ? undefined : { aspectRatio: ratio }
    },
      h("div", { className: "rj-media__inner" }, media),
      props.children ? h("div", { className: "rj-media__overlay" }, props.children) : null,
      playBtn);
  }

  /* ---------- ProjectCard ---------- */

  function ProjectCard(props) {
    var media = props.media || {};
    return h("article", { className: cx("rj-card", props.className) },
      h("div", { className: "rj-card__mediawrap" },
        h(MediaFrame, Object.assign({ ratio: "16/10", radius: "lg" }, media, { className: "rj-card__media" }))),
      h("div", { className: "rj-card__body" },
        props.tags && props.tags.length ? h("div", { className: "rj-card__tags" },
          props.tags.map(function (t, i) { return h(Tag, { key: i, tone: t.tone, icon: t.icon }, t.label); })) : null,
        h("h3", { className: "rj-card__title" },
          h("a", { className: "rj-card__link", href: props.href || "#", target: props.external ? "_blank" : undefined, rel: props.external ? "noopener" : undefined }, props.title)),
        props.formerly ? h("p", { className: "rj-card__formerly" }, "Formerly " + props.formerly) : null,
        props.description ? h("p", { className: "rj-card__desc" }, props.description) : null,
        h("span", { className: "rj-card__action", "aria-hidden": "true" },
          props.action || "Open project",
          h(Icon, { name: props.external ? "arrow-up-right" : "arrow-right", size: 20, className: "rj-card__action-icon rj-btn__icon--" + (props.external ? "arrow-up-right" : "arrow-right") }))));
  }

  /* ---------- LineReveal ---------- */

  function LineReveal(props) {
    var reduced = useReducedMotion();
    var ref = useRef(null);
    var lines = props.lines || String(props.children || "").split("\n");
    var trigger = props.trigger || "view";
    var inView = useInView(ref, trigger === "view" && !reduced);
    var m = useState(false), mounted = m[0], setMounted = m[1];
    useEffect(function () {
      if (trigger !== "mount" || reduced) return;
      var id = requestAnimationFrame(function () { requestAnimationFrame(function () { setMounted(true); }); });
      return function () { cancelAnimationFrame(id); };
    }, [trigger, reduced]);
    var shown = reduced || (trigger === "mount" ? mounted : inView);
    var Tag_ = props.as || "h1";
    return h(Tag_, { ref: ref, className: cx("rj-lines", !reduced && "is-armed", shown && "is-in", props.className), style: props.style },
      h("span", { className: "rj-sr" }, lines.join(" ")),
      lines.map(function (line, i) {
        return h("span", { key: i, className: "rj-line", "aria-hidden": "true" },
          h("span", { className: "rj-line__inner", style: { transitionDelay: "calc(var(--duration-stagger) * " + i + " + " + (props.delay || 0) + "ms)" } }, line));
      }));
  }

  /* ---------- Reveal ---------- */

  function Reveal(props) {
    var reduced = useReducedMotion();
    var ref = useRef(null);
    var a = useState(false), armed = a[0], setArmed = a[1];
    useLayoutEffect(function () { if (!reduced) setArmed(true); }, [reduced]);
    var inView = useInView(ref, armed);
    /* once the group has arrived, drop the reveal rules so children get their own transitions back */
    useEffect(function () {
      if (!inView) return;
      var t = setTimeout(function () { setArmed(false); },
        tokenMs("--duration-slow", 600) + 7 * tokenMs("--duration-stagger", 70) + 120);
      return function () { clearTimeout(t); };
    }, [inView]);
    var Tag_ = props.as || "div";
    var rest = omit(props, ["as", "className", "children"]);
    return h(Tag_, Object.assign({}, rest, { ref: ref, className: cx("rj-reveal", armed && "is-armed", inView && "is-in", props.className) }), props.children);
  }

  /* ---------- HeroCarousel ---------- */

  function HeroCarousel(props) {
    var slides = props.slides || [];
    var n = slides.length;
    var reduced = useReducedMotion();
    var dwell = useRef(props.interval || 6000);
    var is = useState(0), index = is[0], setIndex = is[1];
    var us = useState(true), userPlaying = us[0], setUserPlaying = us[1];
    var hs = useState(false), hovering = hs[0], setHovering = hs[1];
    var fs = useState(false), focused = fs[0], setFocused = fs[1];
    var vs = useState(false), hidden = vs[0], setHidden = vs[1];
    var fills = useRef([]);
    var elapsed = useRef(0);
    var swipe = useRef(null);

    useEffect(function () { if (!props.interval) dwell.current = tokenMs("--duration-dwell", 6000); }, [props.interval]);
    useEffect(function () {
      var on = function () { setHidden(document.hidden); };
      document.addEventListener("visibilitychange", on);
      return function () { document.removeEventListener("visibilitychange", on); };
    }, []);

    var auto = props.autoPlay !== false && !reduced && n > 1;
    var running = auto && userPlaying && !hovering && !focused && !hidden;

    var go = useCallback(function (i) {
      elapsed.current = 0;
      setIndex(((i % n) + n) % n);
    }, [n]);

    useEffect(function () {
      for (var i = 0; i < fills.current.length; i++) {
        var f = fills.current[i];
        if (f) f.style.transform = "scaleX(" + (i === index ? (auto ? Math.min(1, elapsed.current / dwell.current) : 1) : 0) + ")";
      }
      if (!running) return;
      var raf, last = performance.now();
      var tick = function (now) {
        elapsed.current += now - last; last = now;
        var p = Math.min(1, elapsed.current / dwell.current);
        var f = fills.current[index];
        if (f) f.style.transform = "scaleX(" + p + ")";
        if (p >= 1) { go(index + 1); return; }
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
      return function () { cancelAnimationFrame(raf); };
    }, [running, index, go, auto]);

    function onKey(e) {
      if (e.key === "ArrowRight") { e.preventDefault(); go(index + 1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); go(index - 1); }
    }
    function onPointerDown(e) { swipe.current = { x: e.clientX, y: e.clientY }; }
    function onPointerUp(e) {
      var s0 = swipe.current; swipe.current = null;
      if (!s0) return;
      var dx = e.clientX - s0.x, dy = e.clientY - s0.y;
      if (Math.abs(dx) >= 40 && Math.abs(dx) > Math.abs(dy)) go(index + (dx < 0 ? 1 : -1));
    }

    return h("section", {
      className: cx("rj-hero", props.className), "aria-roledescription": "carousel", "aria-label": props.label || "Featured work",
      onKeyDown: onKey,
      onFocus: function (e) { if (!e.currentTarget.contains(e.relatedTarget) && isKeyboardFocus(e.target)) setFocused(true); },
      onBlur: function (e) { if (!e.currentTarget.contains(e.relatedTarget)) setFocused(false); }
    },
      h("div", {
        className: "rj-hero__frame",
        onMouseEnter: function () { setHovering(true); }, onMouseLeave: function () { setHovering(false); },
        onPointerDown: onPointerDown, onPointerUp: onPointerUp
      },
        slides.map(function (s, i) {
          var on = i === index;
          var title = s.lines || [s.title];
          var action = s.action;
          var footage = s.media && (s.media.src || s.media.image);
          return h("div", {
            key: i, className: cx("rj-hero__slide", on && "is-active", footage && "has-footage"), role: "group", "aria-roledescription": "slide",
            "aria-label": (i + 1) + " of " + n + ": " + title.join(" "), "aria-hidden": on ? undefined : "true",
            inert: on ? undefined : ""
          },
            h(MediaFrame, Object.assign({ fill: true, radius: "xl", autoPlay: on }, s.media || {}, { mark: undefined, className: "rj-hero__media" })),
            h("div", { className: "rj-hero__caption" },
              s.formerly ? h("p", { className: "rj-hero__formerly" }, "Formerly " + s.formerly) : null,
              on ? h(LineReveal, { key: "t" + index, as: "h2", lines: title, trigger: "mount", className: "rj-hero__title" })
                : h("h2", { className: "rj-hero__title" }, title.join(" ")),
              s.tagline ? h("p", { className: "rj-hero__tagline" }, s.tagline) : null,
              action ? h(Button, { variant: "inverse", size: "lg", href: action.href, icon: action.external ? "arrow-up-right" : "arrow-right" }, action.label) : null));
        })),
      h("div", { className: "rj-hero__controls" },
        h("div", { className: "rj-hero__segments", role: "group", "aria-label": "Slides" },
          slides.map(function (s, i) {
            var title = (s.lines || [s.title]).join(" ");
            return h("button", {
              key: i, type: "button", className: cx("rj-seg", i === index && "is-active"),
              "aria-label": "Show slide " + (i + 1) + " of " + n + ": " + title, "aria-current": i === index ? "true" : undefined,
              onClick: function () { go(i); }
            }, h("span", { className: "rj-seg__fill", ref: function (el) { fills.current[i] = el; } }));
          })),
        h("div", { className: "rj-hero__buttons" },
          h("button", { type: "button", className: "rj-iconbtn", "aria-label": "Previous slide", onClick: function () { go(index - 1); } }, h(Icon, { name: "chevron-left", size: 24 })),
          auto ? h("button", {
            type: "button", className: "rj-iconbtn", "aria-label": userPlaying ? "Pause slides" : "Play slides",
            onClick: function () { setUserPlaying(!userPlaying); setFocused(false); }
          }, h(Icon, { name: userPlaying ? "pause" : "play", size: 20 })) : null,
          h("button", { type: "button", className: "rj-iconbtn", "aria-label": "Next slide", onClick: function () { go(index + 1); } }, h(Icon, { name: "chevron-right", size: 24 })))));
  }

  /* ---------- SiteHeader ---------- */

  function SiteHeader(props) {
    var links = props.links || [];
    var ss = useState(false), scrolledAuto = ss[0], setScrolled = ss[1];
    var ms = useState(false), open = ms[0], setOpen = ms[1];
    var navRef = useRef(null), indRef = useRef(null);
    var hs = useState(null), hover = hs[0], setHover = hs[1];
    var scrolled = props.scrolled !== undefined ? props.scrolled : scrolledAuto;

    useEffect(function () {
      if (props.scrolled !== undefined) return;
      var on = function () { setScrolled(window.scrollY > 8); };
      on();
      window.addEventListener("scroll", on, { passive: true });
      return function () { window.removeEventListener("scroll", on); };
    }, [props.scrolled]);

    var currentIndex = -1;
    links.forEach(function (l, i) { if (l.current) currentIndex = i; });
    var target = hover !== null ? hover : currentIndex;

    var place = useCallback(function () {
      var nav = navRef.current, ind = indRef.current;
      if (!nav || !ind) return;
      var a = target >= 0 ? nav.querySelectorAll(".rj-nav__link")[target] : null;
      if (!a) { ind.style.opacity = "0"; return; }
      ind.style.opacity = "1";
      ind.style.width = a.offsetWidth + "px";
      ind.style.transform = "translateX(" + a.offsetLeft + "px)";
    }, [target]);
    useLayoutEffect(function () { place(); }, [place]);
    useEffect(function () {
      var on = function () { place(); };
      window.addEventListener("resize", on);
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(on);
      var id = requestAnimationFrame(function () { if (indRef.current) indRef.current.classList.add("is-ready"); });
      return function () { window.removeEventListener("resize", on); cancelAnimationFrame(id); };
    }, [place]);

    var action = props.action;
    return h("header", { className: cx("rj-header", scrolled && "is-scrolled", props.sticky === false && "rj-header--static", props.className) },
      h("div", { className: "rj-header__inner" },
        h("a", { className: "rj-wordmark", href: props.href || "/" }, props.name || "Rohan Jayapalan"),
        h("nav", { className: "rj-nav", "aria-label": props.navLabel || "Main" },
          h("div", { className: "rj-nav__list", ref: navRef, onMouseLeave: function () { setHover(null); } },
            h("span", { className: "rj-nav__indicator", ref: indRef, "aria-hidden": "true" }),
            links.map(function (l, i) {
              return h("a", {
                key: i, className: cx("rj-nav__link", l.current && "is-current"), href: l.href,
                "aria-current": l.current ? "page" : undefined,
                onMouseEnter: function () { setHover(i); }, onFocus: function () { setHover(i); }, onBlur: function () { setHover(null); }
              }, l.label);
            }))),
        h("div", { className: "rj-header__end" },
          action ? h(Button, { variant: "secondary", size: "md", href: action.href, className: "rj-header__action", icon: action.external ? "arrow-up-right" : undefined }, action.label) : null,
          links.length ? h("button", {
            type: "button", className: "rj-iconbtn rj-header__menu", "aria-expanded": open ? "true" : "false",
            "aria-label": open ? "Close menu" : "Open menu", onClick: function () { setOpen(!open); }
          }, h(Icon, { name: open ? "x" : "menu", size: 24 })) : null)),
      open ? h("div", { className: "rj-header__panel" },
        links.map(function (l, i) {
          return h("a", { key: i, className: "rj-header__panel-link", href: l.href, "aria-current": l.current ? "page" : undefined }, l.label);
        }),
        action ? h(Button, { variant: "primary", size: "lg", href: action.href }, action.label) : null) : null);
  }

  /* ---------- LinkPanel ---------- */

  function LinkPanel(props) {
    var icon = props.icon || (props.external ? "arrow-up-right" : "arrow-right");
    return h("a", {
      className: cx("rj-panel", props.className), href: props.href || "#",
      target: props.external ? "_blank" : undefined, rel: props.external ? "noopener" : undefined
    },
      h("span", { className: "rj-panel__text" },
        h("span", { className: "rj-panel__title" }, props.title),
        props.description ? h("span", { className: "rj-panel__desc" }, props.description) : null),
      h("span", { className: "rj-panel__icon rj-btn__icon--" + icon, "aria-hidden": "true" }, h(Icon, { name: icon, size: 24 })));
  }

  var api = {
    Button: Button, Tag: Tag, FilterChips: FilterChips, MediaFrame: MediaFrame, ProjectCard: ProjectCard,
    HeroCarousel: HeroCarousel, LineReveal: LineReveal, Reveal: Reveal, SiteHeader: SiteHeader, LinkPanel: LinkPanel,
    Icon: Icon
  };
  window.RJ = Object.assign(window.RJ || {}, api);
})();
