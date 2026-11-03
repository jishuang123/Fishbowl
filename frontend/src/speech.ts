import { currentCharacter as character } from './character';
/** Audio envelope only; never writes mouth values into the model's saved pose. */
export class SpeechMouth {
  private audio: any;
  private speaking = false;
  private target = 0;
  private level = 0;
  private lastSignal = 0;
  private lastFrame = 0;
  private mouthSlot = (value: number) => {
    this.target = Math.max(0,Math.min(.85,value));
    this.lastSignal = performance.now();
  };
  private speakingSlot = (speaking: boolean) => {
    this.speaking = speaking;
    this.lastSignal = performance.now();
    if (!speaking) this.target = this.level = 0;
  };
  private muteSlot = (muted: boolean) => { if (muted) this.speakingSlot(false); };

  constructor(private sample: any) {}

  connect(audio: any) {
    if (!audio) return;
    this.audio = audio;
    this.speaking = audio.speaking && !audio.muted;
    audio.mouthChanged.connect(this.mouthSlot);
    audio.speakingChanged.connect(this.speakingSlot);
    audio.mutedChanged.connect(this.muteSlot);
  }

  frame(now: number) {
    const model = this.sample.getLive2DManager()._models[0];
    if (!model) return;
    const active = this.speaking && now-this.lastSignal<500;
    const dt = Math.min(.1,Math.max(0,(now-this.lastFrame)/1000));
    this.lastFrame = now;
    this.level = active ? this.level+(this.target-this.level)*(1-Math.exp(-dt/0.06)) : 0;
    model.mouthActive = active;
    model.mouthLevel = this.level;
  }

  snapshot() {
    const core = this.sample.getLive2DManager()._models[0]?.getModel();
    const parameters: Record<string,any> = {};
    if (core) for (const id of [character.mouth.open,character.mouth.jaw,'ParamMouthForm'].filter(Boolean)) {
      const index = core._model.parameters.ids.indexOf(id);
      if (index>=0) parameters[id] = {value:core.getParameterValueByIndex(index),
        min:core.getParameterMinimumValue(index),max:core.getParameterMaximumValue(index),
        default:core.getParameterDefaultValue(index)};
    }
    return {speaking:this.speaking,level:this.level,parameters};
  }

  dispose() {
    this.speakingSlot(false);
    this.audio?.mouthChanged.disconnect(this.mouthSlot);
    this.audio?.speakingChanged.disconnect(this.speakingSlot);
    this.audio?.mutedChanged.disconnect(this.muteSlot);
  }
}
