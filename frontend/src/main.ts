import { LAppDelegate } from '../vendor/lappdelegate';
import { PetInteractions } from './interactions';
import { SpeechMouth } from './speech';
import { loadCharacter,currentCharacter } from './character';
import { LAppPal } from '../vendor/lapppal';

declare global {
  interface Window { qt?: any; QWebChannel?: any; fishbowl: any; }
}

let bridge: any;
let interactions: PetInteractions;
let speech: SpeechMouth;
const status = document.getElementById('status')!;
const errors: string[] = [];
const requestedCharacter = new URLSearchParams(location.search).get('character') ?? 'deepseek';
function fail(message: string) {
  errors.push(message);
  status.textContent = `入缸失败：${message}。右键可退出，详细信息见运行日志。`;
  status.hidden = false;
  bridge?.report(JSON.stringify({ error: message, character: requestedCharacter }));
}
window.addEventListener('error', event => fail(event.message));
window.addEventListener('unhandledrejection', event => fail(String(event.reason)));
const originalLog = console.log.bind(console);
console.log = (...args: any[]) => {
  originalLog(...args);
  const text = args.map(String).join(' ');
  if (text.includes('[CSM][E]') && errors.length === 0) fail(text);
};

function connectDesktop() {
  if (!window.qt) return;
  const script = document.createElement('script');
  script.src = '/qtwebchannel.js';
  script.onload = () => new window.QWebChannel(window.qt.webChannelTransport, (channel: any) => {
    bridge = channel.objects.pet;
    // Native audio signals carry only playback state and amplitude, never text or keys.
    window.fishbowl.audio = channel.objects.audio;
    speech?.connect(channel.objects.audio);
    interactions?.connect(bridge);
    if (ready) bridge.report(JSON.stringify({ready:true,character:requestedCharacter}));
    else if (errors.length) bridge.report(JSON.stringify({error:errors[0],character:requestedCharacter}));
  });
  script.onerror = () => fail('桌面通信连接失败');
  document.head.append(script);
}

const ranges: Record<string, number[]> = {};
let frames = 0;
let ready = false;
let lastPixels: number[] = [];
const started = performance.now();
window.fishbowl = { snapshot: () => ({ ready, errors, frames, ranges }) };

window.addEventListener('load', async () => {
  connectDesktop();
  try {
    await loadCharacter();
    document.title = `Fishbowl · ${currentCharacter.name}`;
    const delegate = LAppDelegate.getInstance();
    if (!delegate.initialize()) throw new Error('无法初始化 WebGL');
    delegate.run();
    const sample = (delegate as any)._subdelegates[0];
    interactions = new PetInteractions(sample);
    speech = new SpeechMouth(sample);
    if (bridge) interactions.connect(bridge);
    if (window.fishbowl.audio) speech.connect(window.fishbowl.audio);
    const gl = sample.getGlManager().getGl() as WebGL2RenderingContext;
    const debug = gl.getExtension('WEBGL_debug_renderer_info');
    const renderer = debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    document.addEventListener('visibilitychange', () => LAppPal.updateTime());
    sample.getCanvas().addEventListener('webglcontextlost', () => fail('图形上下文丢失，请退出后重试'));
    let lastSample = 0;
    const inspect = (now: number) => {
      frames++;
      interactions.frame(now);
      speech.frame(now);
      const model = sample.getLive2DManager()._models[0];
      if (model?._state === 23 && now - lastSample > 100) {
        lastSample = now;
        const core = model.getModel();
        for (const id of ['ParamEyeLOpen', 'ParamEyeROpen', 'ParamBreath']) {
          const index = core._model.parameters.ids.indexOf(id);
          if (index < 0) continue;
          const value = core.getParameterValueByIndex(index);
          const range = ranges[id] ?? [value, value];
          ranges[id] = [Math.min(range[0], value), Math.max(range[1], value)];
        }
        // Read the default framebuffer while the rendered frame is still available.
        if (!ready && errors.length === 0) {
          const pixel = new Uint8Array(4);
          gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
          lastPixels = [...pixel];
          ready = true; status.hidden = true; bridge?.report(JSON.stringify({ ready: true, character: requestedCharacter }));
        }
      }
      if (!ready && now - started > 45000 && errors.length === 0) fail('加载超时');
    };
    // Run inside the renderer's RAF, before Chromium presents/clears the
    // default framebuffer. A separate RAF is not a reliable pixel-hit seam.
    sample.onFrameRendered = inspect;
    window.fishbowl.snapshot = () => ({
      ready, errors, frames, ranges, cornerPixel: lastPixels, interaction: interactions.snapshot(), speech:speech.snapshot(),
      character: currentCharacter.id,
      textures: modelCount(), parameters: sample.getLive2DManager()._models[0]?.getModel()?.getParameterCount(),
      renderer, maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE), contextLost: gl.isContextLost(),
      glError: gl.getError(), canvas: [sample.getCanvas().width, sample.getCanvas().height],
    });
    function modelCount() { return sample.getLive2DManager()._models[0]?._textureCount ?? 0; }
  } catch (error) { fail(String(error)); }
});
window.addEventListener('beforeunload', () => { speech?.dispose(); interactions?.dispose(); LAppDelegate.releaseInstance(); });
