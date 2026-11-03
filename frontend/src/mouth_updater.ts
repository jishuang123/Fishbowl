import { ICubismUpdater,CubismUpdateOrder } from '@framework/motion/icubismupdater';
import { CubismModel } from '@framework/model/cubismmodel';
import { CubismFramework } from '@framework/live2dcubismframework';
import { currentCharacter as character } from './character';

/** Native speech wins over mouth expressions, and still drives jaw physics. */
export class NativeMouthUpdater extends ICubismUpdater {
  constructor(private source: {mouthActive: boolean; mouthLevel: number}) {
    super(CubismUpdateOrder.CubismUpdateOrder_Physics-1);
  }
  onLateUpdate(model: CubismModel): void {
    if (!this.source.mouthActive) return;
    const mouth = character.mouth;
    for (const [id,scale] of [[mouth.open,1],[mouth.jaw,mouth.jaw_scale]] as [string,number][]) {
      if (!id) continue;
      const index = model.getParameterIndex(CubismFramework.getIdManager().getId(id));
      if (index>=0 && index<model.getParameterCount()) model.setParameterValueByIndex(index,this.source.mouthLevel*scale);
    }
  }
}
