import { IdleSchedule } from './idle';
import { currentCharacter as character } from './character';
import type { Binding,Trigger } from './character';
import type { CubismMotion } from '@framework/motion/cubismmotion';

type Source = 'manual' | 'idle';
/** Owns pointer intent and the curated, reversible model interactions. */
export class PetInteractions {
  private bridge: any;
  private down: {x: number; y: number; id: number} | null = null;
  private dragged = false;
  private gaze = {x: 0, y: 0};
  private pendingClick: {x: number; y: number} | null = null;
  private expressionIndex = 0;
  private expressionUntil = 0;
  private holdUntil = 0;
  private lastClick = -Infinity;
  private restore = false;
  private gestureBaseline: [number, number][] = [];
  private phase = 'idle';
  private expression = 'Neutral';
  private history: string[] = [];
  private disposed = false;
  private idle = new IdleSchedule();
  private desktopPaused = false;
  private expressionSource: Source | null = null;
  private gestureSource: Source | null = null;
  private gestureEpoch = 0;
  private idleCount = 0;
  private idleHistory: {kind: string; at: number}[] = [];
  private lastIdleExpression = '';
  private customExpression = false;
  private customDeadline = 0;
  private partBaseline: [number,number][] = [];
  private restoreLoop?: () => void;
  private bindingsSlot = (message: string) => {
    const value = JSON.parse(message);
    if (value.character !== character.id) return;
    this.interruptIdle();
    if (this.phase !== 'idle') {
      this.gestureEpoch++; this.model()?._motionManager.stopAllMotions();
      this.phase = 'idle'; this.gestureSource = null; this.restore = true;
    }
    if (this.customExpression) this.resetExpression();
    character.bindings = value.bindings;
    this.idle.defer(performance.now());
  };
  private pauseSlot = (paused: boolean) => {
    this.desktopPaused = paused;
    if (paused) this.bridge?.stopIdleVoice();
    this.interruptIdle();
    this.idle.defer(performance.now());
  };
  private abort = new AbortController();
  private gazeSlot = (x: number, y: number) => this.setGaze(x, y);

  constructor(private sample: any) {
    const listen = (type: string, listener: EventListener) => document.addEventListener(type, listener, {signal: this.abort.signal});
    listen('pointerdown', ((e: PointerEvent) => {
      this.activity();
      if (e.button !== 0 || !(e.target instanceof HTMLCanvasElement)) return;
      this.down = {x: e.screenX, y: e.screenY, id: e.pointerId};
      this.dragged = false;
      e.target.setPointerCapture(e.pointerId);
    }) as EventListener);
    listen('pointermove', ((e: PointerEvent) => {
      this.idle.defer(performance.now());
      if (!this.bridge) this.localGaze(e.clientX, e.clientY);
      if (!this.down || this.down.id !== e.pointerId) return;
      if (!this.dragged && Math.hypot(e.screenX-this.down.x, e.screenY-this.down.y) >= 6) {
        this.dragged = true;
        this.bridge?.beginDrag(this.down.x, this.down.y);
      }
      if (this.dragged) this.bridge?.drag(e.screenX, e.screenY);
    }) as EventListener);
    listen('pointerup', ((e: PointerEvent) => {
      this.idle.defer(performance.now());
      if (e.button !== 0 || !this.down || this.down.id !== e.pointerId) return;
      const moved = Math.hypot(e.screenX-this.down.x, e.screenY-this.down.y) >= 6;
      if (this.dragged) this.bridge?.endDrag(e.screenX, e.screenY);
      else if (!moved) this.pendingClick = {x: e.clientX, y: e.clientY};
      this.down = null;
      this.dragged = false;
    }) as EventListener);
    listen('pointercancel', () => this.cancel());
    listen('lostpointercapture', () => this.cancel());
    listen('contextmenu', e => { e.preventDefault(); this.cancel(); this.bridge?.showMenu(); });
    document.addEventListener('pointerleave', () => { if (!this.bridge && !this.down) this.setGaze(0,0); }, {signal:this.abort.signal});
    window.addEventListener('blur', () => this.cancel(), {signal:this.abort.signal});
    document.addEventListener('visibilitychange', () => {
      this.interruptIdle(); this.idle.defer(performance.now());
    }, {signal:this.abort.signal});
  }

  connect(bridge: any) {
    if (this.disposed) return;
    this.bridge = bridge;
    bridge.gazeChanged.connect(this.gazeSlot);
    bridge.idlePausedChanged.connect(this.pauseSlot);
    bridge.bindingsChanged.connect(this.bindingsSlot);
    bridge.requestBindings();
    bridge.requestIdleState();
  }

  private model() { return this.sample.getLive2DManager()._models[0]; }
  private setGaze(x: number, y: number) {
    this.gaze = {x: Math.max(-1,Math.min(1,x)), y: Math.max(-1,Math.min(1,y))};
  }
  private localGaze(x: number, y: number) {
    const box = this.sample.getCanvas().getBoundingClientRect();
    this.setGaze((x-box.left-box.width*.5)/(box.width*.7), (box.top+box.height*.23-y)/(box.height*.5));
  }
  private cancel() {
    this.down = null; this.dragged = false; this.bridge?.cancelDrag();
    this.activity();
  }

  private activity() {
    this.bridge?.stopIdleVoice();
    this.idle.defer(performance.now());
    this.interruptIdle();
  }

  private interruptIdle() {
    const model = this.model();
    if (this.expressionSource === 'idle') {
      this.resetExpression();
    }
    if (this.gestureSource === 'idle') {
      this.gestureEpoch++;
      model?._motionManager.stopAllMotions();
      this.phase = 'idle'; this.gestureSource = null; this.restore = true;
    }
  }

  private resetExpression() {
    const model = this.model();
    if (this.customExpression) model?._expressionManager.stopAllMotions();
    if (character.expressions.neutral) model?.setExpression(character.expressions.neutral);
    this.customExpression = false;
    this.expression = 'Neutral'; this.expressionUntil = 0; this.expressionSource = null;
  }

  private runBinding(key: Trigger, now: number) {
    const binding = character.bindings?.[key];
    if (!binding || binding.mode === 'default') return false;
    if (binding.mode === 'off') return true;
    if (binding.action && this.phase !== 'idle') return true;
    const source = key === 'idle' ? 'idle' : 'manual';
    if (binding.action?.kind === 'gesture') this.startGesture(source);
    else if (binding.action?.kind === 'motion') this.startCustomMotion(binding,source,now);
    if (binding.expression) {
      this.model()._expressionManager.stopAllMotions();
      this.customExpression = true;
      this.showExpression(binding.expression,source,now);
    }
    if (binding.voice) this.bridge?.triggerInteraction(character.id,key);
    const kind = [binding.action?.label,binding.expression,binding.voice ? 'Voice' : ''].filter(Boolean).join(' + ');
    if (kind) {
      if (source === 'manual') this.history = [...this.history,kind].slice(-12);
      else {
        this.idleCount++;
        this.idleHistory = [...this.idleHistory,{kind,at:now}].slice(-12);
      }
    }
    return true;
  }

  private startCustomMotion(binding: Binding, source: Source, now: number) {
    const action = binding.action!;
    const model = this.model(), core = model.getModel();
    const motion = model._motions.get(`${action.group}_${action.index}`) as CubismMotion | undefined;
    if (!motion) return;
    // Capture the saved base, rather than baking gaze/physics/speech into it.
    core.loadParameters();
    this.gestureBaseline = (action.parameters ?? []).flatMap(id => {
      const index = core._model.parameters.ids.indexOf(id);
      return index < 0 ? [] : [[index,core.getParameterValueByIndex(index)] as [number,number]];
    });
    this.partBaseline = (action.parts ?? []).flatMap(id => {
      const index = core._model.parts.ids.indexOf(id);
      return index < 0 ? [] : [[index,core.getPartOpacityByIndex(index)] as [number,number]];
    });
    const loop = motion.getLoop();
    motion.setLoop(false);
    this.restoreLoop = () => motion.setLoop(loop);
    this.gestureSource = source; this.phase = 'custom';
    this.customDeadline = now+Math.min(12000,action.duration_ms ?? 12000);
    const epoch = ++this.gestureEpoch;
    model.startMotion(action.group,action.index,3,() => {
      if (this.disposed || epoch !== this.gestureEpoch) return;
      this.phase = 'idle'; this.gestureSource = null; this.restore = true;
    });
  }

  private showExpression(name: string, source: Source, now: number) {
    this.expression = name; this.expressionSource = source;
    this.model().setExpression(name);
    this.expressionUntil = now + (source === 'idle' ? 2000 : 2500);
  }

  private startGesture(source: Source) {
    const model = this.model(), core = model.getModel();
    const gesture = character.gesture;
    if (!gesture) return;
    const ids: string[] = gesture.parameters;
    this.gestureBaseline = ids.flatMap(id => {
      const index = core._model.parameters.ids.indexOf(id);
      return index < 0 ? [] : [[index, core.getParameterValueByIndex(index)] as [number,number]];
    });
    const epoch = ++this.gestureEpoch;
    this.gestureSource = source; this.phase = 'raise';
    model.startMotion(gesture.group, gesture.enter, 3, () => {
      if (this.disposed || epoch !== this.gestureEpoch) return;
      this.phase = 'hold'; this.holdUntil = performance.now()+gesture.hold_ms;
    });
  }

  private maybeIdle(now: number) {
    const binding = character.bindings?.idle;
    if (binding?.mode === 'off') return;
    const available: string[] = character.expressions.idle;
    if (binding?.mode !== 'custom' && !available.length && !character.gesture) return;
    const blocked = this.disposed || document.hidden || this.desktopPaused || !!this.down ||
      this.dragged || !!this.pendingClick || this.phase !== 'idle' || this.expression !== 'Neutral';
    if (!this.idle.due(now, blocked)) return;
    if (this.runBinding('idle',now)) return;
    const previous = this.idleHistory.at(-1)?.kind;
    let kind: string;
    if (available.length && (!character.gesture || Math.random() < .8 || previous === character.gesture?.name)) {
      let choices = available.filter(name => name !== this.lastIdleExpression);
      if (!choices.length) choices = available;
      kind = choices[Math.floor(Math.random()*choices.length)];
      this.lastIdleExpression = kind;
      this.showExpression(kind, 'idle', now);
    } else if (character.gesture) {
      kind = character.gesture.name; this.startGesture('idle');
    } else return;
    this.idleCount++;
    this.idleHistory.push({kind, at:now});
    this.idleHistory = this.idleHistory.slice(-12);
  }

  /** Called after the actual render, so hit testing samples the visible frame. */
  frame(now: number) {
    const model = this.model();
    if (model?._state !== 23) return;
    this.sample.getLive2DManager().onDrag(this.dragged ? 0 : this.gaze.x*.8, this.dragged ? 0 : this.gaze.y*.8);
    if (this.restore) {
      const core = model.getModel();
      // Restore only motion-owned baseline values. Saving the rendered frame
      // would bake gaze, expression, breath and physics offsets into the base.
      core.loadParameters();
      for (const [index, value] of this.gestureBaseline) core.setParameterValueByIndex(index,value);
      for (const [index, value] of this.partBaseline) core.setPartOpacityByIndex(index,value);
      this.partBaseline = [];
      this.restoreLoop?.(); this.restoreLoop = undefined;
      core.saveParameters();
      this.restore = false;
    }
    if (this.expressionUntil && now >= this.expressionUntil) {
      this.resetExpression();
    }
    if (this.phase === 'custom' && now >= this.customDeadline) {
      this.gestureEpoch++; model._motionManager.stopAllMotions();
      this.phase = 'idle'; this.gestureSource = null; this.restore = true;
    }
    if (this.phase === 'hold' && now >= this.holdUntil && character.gesture) {
      this.phase = 'return';
      const epoch = this.gestureEpoch;
      model.startMotion(character.gesture.group, character.gesture.exit, 3, () => {
        if (this.disposed || epoch !== this.gestureEpoch) return;
        this.phase = 'idle'; this.gestureSource = null; this.restore = true;
      });
    }
    const click = this.pendingClick;
    this.pendingClick = null;
    if (click && now-this.lastClick >= 250) this.handleClick(click, now);
    this.maybeIdle(now);
  }

  private handleClick(click: {x: number; y: number}, now: number) {
    if (this.desktopPaused || document.hidden) return;
    const canvas = this.sample.getCanvas() as HTMLCanvasElement;
    const box = canvas.getBoundingClientRect();
    const x = Math.floor((click.x-box.left)*canvas.width/box.width);
    const y = canvas.height-1-Math.floor((click.y-box.top)*canvas.height/box.height);
    if (x<0 || y<0 || x>=canvas.width || y>=canvas.height) return;
    const gl = this.sample.getGlManager().getGl() as WebGL2RenderingContext;
    const pixel = new Uint8Array(4);
    gl.readPixels(x,y,1,1,gl.RGBA,gl.UNSIGNED_BYTE,pixel);
    if (pixel[3] < 32) return; // Transparent background is not the pet.
    this.lastClick = now;
    const key = (click.y-box.top)/box.height < .35 ? 'head' : 'body';
    if (this.runBinding(key,now)) return;
    if (this.customExpression) this.resetExpression();
    if ((click.y-box.top)/box.height < .35) {
      const choices = character.expressions.manual;
      if (!choices.length) return;
      this.showExpression(choices[this.expressionIndex++ % choices.length], 'manual', now);
      this.history.push(this.expression);
    } else if (this.phase === 'idle' && character.gesture) {
      this.startGesture('manual');
      this.history.push(character.gesture.name);
    }
    this.history = this.history.slice(-12);
  }

  snapshot() {
    const model = this.model();
    const core = model?.getModel();
    const values: Record<string,number> = {};
    const owned = Object.values(character.bindings ?? {}).flatMap(binding => binding.action?.parameters ?? []);
    if (core) for (const id of new Set(['AngleX','AngleY','ParamAngleX','ParamAngleY','ParamEyeBallX','ParamEyeBallY','Movement2','key7','key4','key5','key9',...owned])) {
      const index = core._model.parameters.ids.indexOf(id);
      if (index < 0) continue;
      values[id] = core.getParameterValueByIndex(index);
    }
    return {gaze: this.gaze, phase: this.phase, expression:this.expression, history:[...this.history], values,
      idle: {count:this.idleCount, nextAt:this.idle.nextAt, paused:this.desktopPaused || document.hidden,
        active:this.expressionSource === 'idle' || this.gestureSource === 'idle', history:[...this.idleHistory]}};
  }

  dispose() {
    this.disposed = true;
    this.cancel(); this.abort.abort();
    this.bridge?.gazeChanged.disconnect(this.gazeSlot);
    this.bridge?.idlePausedChanged.disconnect(this.pauseSlot);
    this.bridge?.bindingsChanged.disconnect(this.bindingsSlot);
  }
}
