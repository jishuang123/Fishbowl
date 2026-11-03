/** Keep desktop rendering at 30 FPS and suspend hidden pages without catch-up. */
export class FrameClock {
  private last = 0;
  private readonly period = 1000/30;
  due(now: number, hidden: boolean) {
    if (hidden) { this.last = 0; return false; }
    if (!this.last || now-this.last > 1000) { this.last = now; return true; }
    const delta = now-this.last;
    if (delta < this.period-.5) return false;
    this.last = now-(delta>=this.period ? delta%this.period : 0);
    return true;
  }
}
