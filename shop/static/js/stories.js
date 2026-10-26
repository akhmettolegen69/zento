(function () {
  var dataEl = document.getElementById('story-data');
  var viewer = document.getElementById('viewer');
  if (!dataEl || !viewer) return;
  var data = JSON.parse(dataEl.textContent);
  var img = viewer.querySelector('.v-img'), caption = viewer.querySelector('.v-caption');
  var bars = viewer.querySelector('.bars'), link = viewer.querySelector('.v-link');
  var DURATION = 5000, order = Object.keys(data), si = 0, idx = 0, timer = null;

  function show() {
    var story = data[order[si]], slide = story.slides[idx];
    img.src = slide.img; caption.textContent = slide.caption || '';
    link.hidden = !story.link; if (story.link) link.href = story.link;
    bars.innerHTML = story.slides.map(function (_, i) {
      return '<i class="' + (i < idx ? 'done' : '') + '"><b' + (i === idx ? ' style="animation-duration:' + DURATION + 'ms"' : '') + '></b></i>';
    }).join('');
    clearTimeout(timer); timer = setTimeout(next, DURATION);
  }
  function next() {
    if (idx < data[order[si]].slides.length - 1) idx++;
    else if (si < order.length - 1) { si++; idx = 0; }
    else return close();
    show();
  }
  function prev() {
    if (idx > 0) idx--; else if (si > 0) { si--; idx = 0; }
    show();
  }
  function close() { clearTimeout(timer); viewer.hidden = true; document.body.style.overflow = ''; }

  document.querySelectorAll('.story').forEach(function (b) {
    b.addEventListener('click', function () {
      si = order.indexOf(b.dataset.story); idx = 0;
      viewer.hidden = false; document.body.style.overflow = 'hidden'; show();
    });
  });
  viewer.querySelector('.v-next').onclick = next;
  viewer.querySelector('.v-prev').onclick = prev;
  viewer.querySelector('.v-close').onclick = close;
  viewer.addEventListener('click', function (e) { if (e.target === viewer) close(); });
  document.addEventListener('keydown', function (e) {
    if (viewer.hidden) return;
    if (e.key === 'Escape') close(); else if (e.key === 'ArrowRight') next(); else if (e.key === 'ArrowLeft') prev();
  });
})();
