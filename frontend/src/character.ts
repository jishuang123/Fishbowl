import defaults from '../../characters/generic.json';

interface Gesture {
  group: string; enter: number; exit: number; name: string; hold_ms: number;
  parameters: string[];
}
export type Trigger = 'head' | 'body' | 'idle';
export interface Binding {
  mode: 'default' | 'off' | 'custom';
  action: {kind: 'gesture' | 'motion'; group?: string; index?: number; label: string;
    parameters?: string[]; parts?: string[]; duration_ms?: number} | null;
  expression: string; voice: boolean;
}
export interface CharacterProfile {
  id: string; name: string; model_url: string; mask_buffers: number;
  blink_while_motion: boolean;
  tracking: {x: string; y: string; z: string};
  mouth: {open: string; jaw: string; jaw_scale: number};
  expressions: {neutral: string; manual: string[]; idle: string[]};
  gesture: Gesture | null;
  bindings?: Record<Trigger,Binding>;
}

// Only the rendering/interaction projection is exposed to the web page.
export const currentCharacter: CharacterProfile = {...defaults,id:'',name:''};

export async function loadCharacter() {
  const id = new URLSearchParams(location.search).get('character') ?? 'deepseek';
  const response = await fetch(`/character-profile.json?id=${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error('无法读取角色配置');
  const profile = await response.json();
  Object.assign(currentCharacter,profile);
}
