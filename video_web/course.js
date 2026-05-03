// Course data loader — reads from a tenant-scoped course folder.
// Usage:  index.html?persona=zoominfo/the_autonomous_architect
//         index.html?persona=the_leadership_blueprint/architect
// `persona` is the path (relative to video_web/) of the course folder.

(function () {
  'use strict';

  const params  = new URLSearchParams(window.location.search);
  const persona = params.get('persona') || 'zoominfo/the_disengaged_kinesthetic';
  const jsonUrl = `${persona}/course.json`;

  // Body class so styles.css can scope per-tenant tweaks
  const tenantSlug = persona.split('/')[0].replace(/_/g, '-');
  document.body.classList.add('tenant-' + tenantSlug);

  fetch(jsonUrl)
    .then(res => {
      if (!res.ok) throw new Error(`Failed to load ${jsonUrl} (${res.status})`);
      return res.json();
    })
    .then(data => {
      // Prefix every relative path with the course folder so the player
      // can resolve videos/ and slides/ correctly.
      const base = `${persona}/`;
      data.slides.forEach(slide => {
        if (slide.avatar) slide.avatar = base + slide.avatar;
        if (slide.main && slide.main.src) slide.main.src = base + slide.main.src;
        if (slide.frames) {
          slide.frames.forEach(f => { if (f.src) f.src = base + f.src; });
        }
      });

      window.COURSE_DATA = data;

      // Dispatch a custom event so player.js knows data is ready
      window.dispatchEvent(new Event('courseDataReady'));
    })
    .catch(err => {
      console.error('[CourseLoader]', err);
      document.body.innerHTML =
        `<div style="color:#fff;padding:3rem;font-family:sans-serif;">
           <h2>⚠️ Could not load course data</h2>
           <p>${err.message}</p>
           <p>Make sure you are serving via a local HTTP server and the
              course folder exists at <code>${persona}/</code>.</p>
         </div>`;
    });
})();
