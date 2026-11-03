"""Exercise the official sample with installed Chrome; retain local evidence."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:5000')
parser.add_argument('--name', default='official-web')
args = parser.parse_args()
out = Path('.local/evidence')
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    page = browser.new_page(viewport={'width': 640, 'height': 800}, device_scale_factor=1)
    logs, errors, failed = [], [], []
    page.on('console', lambda msg: logs.append(f'{msg.type}: {msg.text}'))
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('response', lambda r: failed.append(f'{r.status} {r.url}') if r.status >= 400 else None)
    page.goto(args.url)
    page.evaluate("""async () => {
      const {LAppDelegate} = await import('/src/lappdelegate.ts');
      window.sample = LAppDelegate.getInstance()._subdelegates[0];
    }""")
    page.wait_for_function('window.sample._live2dManager._models[0]?._textureCount === 5', timeout=120000)
    page.wait_for_timeout(4000)
    state = page.evaluate("""() => {
      const s=window.sample, m=s._live2dManager._models[0], gl=s._glManager.getGl();
      const debug=gl.getExtension('WEBGL_debug_renderer_info');
      return {textures:m._textureCount, state:m._state, parameters:m.getModel().getParameterCount(),
        drawables:m.getModel().getDrawableCount(), maxTextureSize:gl.getParameter(gl.MAX_TEXTURE_SIZE),
        renderer:debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),
        contextLost:gl.isContextLost(), glError:gl.getError(),
        canvas:[s._canvas.width,s._canvas.height]};
    }""")
    # Capture the actual composed frame, not just a successful HTTP response.
    page.screenshot(path=str(out / f'{args.name}.png'), omit_background=True)
    values = page.evaluate("""() => new Promise(resolve => {
      const values=[];
      const timer=setInterval(() => {
        const m=window.sample._live2dManager._models[0].getModel();
        values.push(['ParamEyeLOpen','ParamEyeROpen','ParamBreath'].map(
          id=>m.getParameterValueByIndex(m._model.parameters.ids.indexOf(id))));
        if(values.length>=120){clearInterval(timer);resolve(values);}
      },100);
    })""")
    state['parameterRanges'] = {k:[min(row[i] for row in values),max(row[i] for row in values)]
        for i,k in enumerate(['ParamEyeLOpen','ParamEyeROpen','ParamBreath'])}
    sdk_errors = [line for line in logs if '[CSM][E]' in line or line.startswith('error:')]
    state.update(errors=errors, failedResponses=failed, sdkErrors=sdk_errors)
    (out / f'{args.name}.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    (out / f'{args.name}.log').write_text('\n'.join(logs), encoding='utf-8')
    print(json.dumps(state, indent=2))
    browser.close()
    assert not errors and not failed and not sdk_errors and not state['contextLost'] and state['glError'] == 0
