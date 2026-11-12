// Run on the current page with a Playwright-compatible run-code adapter.
// Observes callbacks and public output; it does not drive or repair the app.
async (page) => {
  const driverStart = Date.now();
  const sample = await page.evaluate(() => new Promise(resolve => {
    const start = performance.now();
    let last = start;
    let callbacks = 0;
    let maximumGap = 0;
    let nextFrame;
    const frame = now => {
      callbacks += 1;
      maximumGap = Math.max(maximumGap, now - last);
      last = now;
      nextFrame = requestAnimationFrame(frame);
    };
    nextFrame = requestAnimationFrame(frame);
    setTimeout(() => {
      cancelAnimationFrame(nextFrame);
      const end = performance.now();
      resolve({
        pageElapsedMs: end - start,
        callbacks,
        callbackFps: callbacks * 1000 / (end - start),
        maximumFrameGapMs: Math.max(maximumGap, end - last),
        callbacksAreNotProofOfRenderedWork: true,
        page: {
          url: location.href,
          title: document.title,
          visibility: document.visibilityState,
          viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
          canvases: Array.from(document.querySelectorAll('canvas'), canvas => {
            const box = canvas.getBoundingClientRect();
            return { width: canvas.width, height: canvas.height,
              visibleWidth: box.width, visibleHeight: box.height };
          }),
          publicText: document.body?.innerText?.slice(0, 8000),
        },
      });
    }, 3000);
  }));
  return { ...sample, driverElapsedMs: Date.now() - driverStart };
}
