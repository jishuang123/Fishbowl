/** Low-frequency deadlines, without queued work or catch-up bursts. */
export class IdleSchedule {
  readonly minDelay = 45000;
  readonly maxDelay = 100000;
  nextAt = 0;
  private lastFrame = 0;

  defer(now: number) {
    this.nextAt = now + this.minDelay + Math.random() * (this.maxDelay-this.minDelay);
  }

  due(now: number, blocked: boolean) {
    const resumed = this.lastFrame !== 0 && now-this.lastFrame > 10000;
    this.lastFrame = now;
    if (!this.nextAt || resumed || (blocked && now >= this.nextAt)) this.defer(now);
    if (blocked || now < this.nextAt) return false;
    this.defer(now);
    return true;
  }
}
