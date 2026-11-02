(function () {
  var toast = document.getElementById('toast'), toastTimer;
  function say(msg) {
    toast.textContent = msg; toast.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { toast.hidden = true; }, 2200);
  }
  var T = {
    ru: { added: 'Добавлено в корзину', copied: 'Ссылка скопирована' },
    kk: { added: 'Себетке қосылды', copied: 'Сілтеме көшірілді' },
    en: { added: 'Added to cart', copied: 'Link copied' }
  }[document.documentElement.lang] || { added: 'Added to cart', copied: 'Link copied' };

  document.body.addEventListener('cart-added', function () { say(T.added); });

  // Share: native sheet on mobile, clipboard elsewhere.
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-share]');
    if (!b) return;
    var url = new URL(b.dataset.share, location.href).href;
    if (navigator.share) navigator.share({ title: b.dataset.title, url: url }).catch(function () {});
    else if (navigator.clipboard) navigator.clipboard.writeText(url).then(function () { say(T.copied); });
  });

  // Carousels (scroll-snap + arrows + dots). Re-run after htmx loads more posts.
  function initCarousels(root) {
    root.querySelectorAll('[data-carousel]:not([data-ready])').forEach(function (c) {
      c.dataset.ready = '1';
      var track = c.querySelector('.slides'), dots = c.querySelectorAll('.dots i');
      var prev = c.querySelector('.prev'), next = c.querySelector('.next');
      if (!prev) return;
      function idx() { return Math.round(track.scrollLeft / track.clientWidth); }
      function update() {
        var i = idx(), n = dots.length;
        dots.forEach(function (d, k) { d.classList.toggle('on', k === i); });
        prev.hidden = i === 0; next.hidden = i >= n - 1;
      }
      prev.onclick = function () { track.scrollBy({ left: -track.clientWidth, behavior: 'smooth' }); };
      next.onclick = function () { track.scrollBy({ left: track.clientWidth, behavior: 'smooth' }); };
      track.addEventListener('scroll', function () { window.requestAnimationFrame(update); }, { passive: true });
    });
  }
  initCarousels(document);
  document.body.addEventListener('htmx:afterSettle', function () { initCarousels(document); });

  // Close language menus when clicking elsewhere.
  document.addEventListener('click', function (e) {
    document.querySelectorAll('details[open]').forEach(function (d) {
      if (!d.contains(e.target) && !d.classList.contains('filters-wrap')) d.removeAttribute('open');
    });
  });
})();
