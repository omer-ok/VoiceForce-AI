/** Browser signal activity is an estimate, never an acoustic playback measurement. */
export class AudioTurnDetector {
  private localStart: number | null = null;
  private localLast: number | null = null;
  private pendingEnd: number | null = null;
  private remoteStart: number | null = null;
  private remoteLast: number | null = null;
  private remoteActive = false;

  update(now: number, local: boolean, remote: boolean): number | null {
    if (remote) {
      this.remoteStart ??= now;
      this.remoteLast = now;
    } else {
      this.remoteStart = null;
      if (this.remoteLast !== null && now - this.remoteLast >= 300) {
        this.remoteActive = false;
      }
    }

    // Echo and simultaneous speech cannot be attributed reliably.
    if (local && (remote || this.remoteActive)) {
      this.localStart = this.localLast = this.pendingEnd = null;
      if (remote && this.remoteStart !== null && now - this.remoteStart >= 60) {
        this.remoteActive = true;
      }
      return null;
    }

    if (local) {
      this.localStart ??= now;
      this.localLast = now;
      this.pendingEnd = null;
    } else if (this.localStart !== null && this.localLast !== null) {
      const silence = now - this.localLast;
      if (silence >= (remote ? 120 : 600)) {
        if (this.localLast - this.localStart >= 150) this.pendingEnd = this.localLast;
        this.localStart = this.localLast = null;
      }
    }

    if (remote && this.remoteStart !== null && now - this.remoteStart >= 60) {
      if (!this.remoteActive && this.pendingEnd !== null) {
        const delay = this.remoteStart - this.pendingEnd;
        this.pendingEnd = null;
        this.remoteActive = true;
        return delay >= 0 && delay <= 15000 ? delay / 1000 : null;
      }
      this.remoteActive = true;
    }
    if (this.pendingEnd !== null && now - this.pendingEnd > 15000) {
      this.pendingEnd = null;
    }
    return null;
  }
}
