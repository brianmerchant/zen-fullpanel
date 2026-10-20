// Records geometry at DOMContentLoaded and on the first two animation frames,
// so tests can detect a layout shift after the document's first layout.
(() => {
  const sample = (tag) => {
    const nav = document.getElementById("nav");
    const r = nav ? nav.getBoundingClientRect() : null;
    const probe = JSON.parse(document.documentElement.dataset.probe || "[]");
    probe.push({
      tag, navTop: r ? r.top : null,
      rootTop: document.documentElement.getBoundingClientRect().top,
      innerHeight: window.innerHeight, scrollY: window.scrollY,
    });
    // DOM attributes, unlike page expandos, are visible to test sandboxes.
    document.documentElement.dataset.probe = JSON.stringify(probe);
  };
  document.addEventListener("DOMContentLoaded", () => {
    sample("dcl");
    requestAnimationFrame(() => { sample("raf1"); requestAnimationFrame(() => sample("raf2")); });
  });
  addEventListener("click", (e) => {
    e.preventDefault();
    const clicks = JSON.parse(document.documentElement.dataset.clicks || "[]");
    clicks.push({ id: e.target.id || e.target.className || e.target.localName,
                  x: e.clientX, y: e.clientY });
    document.documentElement.dataset.clicks = JSON.stringify(clicks);
  }, true);
})();
