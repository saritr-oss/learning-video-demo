// Course data loader — reads from persona JSON files.
// Usage:  index.html?persona=the_autonomous_architect
//         index.html?persona=the_disengaged_kinesthetic
// Falls back to the_disengaged_kinesthetic if no param is given.

(function () {
  'use strict';

  const params  = new URLSearchParams(window.location.search);
  const persona = params.get('persona') || 'the_disengaged_kinesthetic';
  const jsonUrl = `persona/${persona}/course.json`;

  fetch(jsonUrl)
    .then(res => {
      if (!res.ok) throw new Error(`Failed to load ${jsonUrl} (${res.status})`);
      return res.json();
    })
    .then(data => {
      // Prefix every relative path with the persona folder so the player
      // can resolve videos/ and slides/ correctly.
      const base = `persona/${persona}/`;
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
              <code>persona/</code> folder exists.</p>
         </div>`;
    });
})();
