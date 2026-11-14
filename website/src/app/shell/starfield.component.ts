import { afterNextRender, ChangeDetectionStrategy, Component, DestroyRef, ElementRef, inject, viewChild } from '@angular/core';

// The hero's backdrop: stars drifting towards the viewer, the improbability
// drive engaged. Still when the visitor prefers reduced motion, paused when
// off-screen.
@Component({
  selector: 'app-starfield',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '<canvas #c aria-hidden="true"></canvas>',
  styles: ':host { position: absolute; inset: 0; overflow: hidden; pointer-events: none; } canvas { width: 100%; height: 100%; display: block; }',
})
export class StarfieldComponent {
  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('c');

  constructor() {
    const destroy = inject(DestroyRef);
    afterNextRender(() => {
      const c = this.canvas().nativeElement;
      const ctx = c.getContext('2d');
      if (!ctx) return;
      const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
      const stars = Array.from({ length: 260 }, () => ({ x: Math.random() * 2 - 1, y: Math.random() * 2 - 1, z: Math.random() }));
      const colors = ['#ffffff', '#c4b5fd', '#67e8f9', '#f9a8d4'];
      let w = 0;
      let h = 0;
      let raf = 0;
      let visible = true;
      const resize = () => {
        const dpr = Math.min(devicePixelRatio || 1, 2);
        w = c.clientWidth;
        h = c.clientHeight;
        c.width = w * dpr;
        c.height = h * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      };
      const draw = () => {
        ctx.clearRect(0, 0, w, h);
        const light = document.documentElement.getAttribute('data-theme') === 'light';
        stars.forEach((s, i) => {
          if (!still) {
            s.z -= 0.0016;
            if (s.z <= 0.02) {
              s.z = 1;
              s.x = Math.random() * 2 - 1;
              s.y = Math.random() * 2 - 1;
            }
          }
          const k = 0.6 / s.z;
          const px = w / 2 + s.x * k * w * 0.35;
          const py = h / 2 + s.y * k * h * 0.35;
          if (px < 0 || px > w || py < 0 || py > h) return;
          const r = Math.max(0.3, (1 - s.z) * 2);
          ctx.globalAlpha = Math.min(1, (1 - s.z) * 1.4) * (light ? 0.5 : 0.9);
          ctx.fillStyle = light ? '#7c3aed' : colors[i % colors.length];
          ctx.beginPath();
          ctx.arc(px, py, r, 0, Math.PI * 2);
          ctx.fill();
        });
        if (!still && visible) raf = requestAnimationFrame(draw);
      };
      resize();
      draw();
      const ro = new ResizeObserver(() => {
        resize();
        if (still) draw();
      });
      ro.observe(c);
      const io = new IntersectionObserver(([e]) => {
        visible = e.isIntersecting;
        if (visible && !still) {
          cancelAnimationFrame(raf);
          raf = requestAnimationFrame(draw);
        }
      });
      io.observe(c);
      destroy.onDestroy(() => {
        cancelAnimationFrame(raf);
        ro.disconnect();
        io.disconnect();
      });
    });
  }
}
