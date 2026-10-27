"""
Remotion render module.

Renders Remotion compositions (TypeScript/React) to mp4 with exact data.
Used for: charts, counters, split-screens, title cards, maps.

Called from orchestrator instead of Flux AI image generation for:
- visual_type in ('remotion_counter', 'remotion_chart', 'remotion_split', 'remotion_title', 'remotion_map')
"""
import os
import subprocess, json
from pathlib import Path


# REMOTION_DIR из env (Railway: /app/remotion), иначе — remotion/ в репозитории.
REMOTION_DIR = Path(os.getenv(
    'REMOTION_DIR',
    Path(__file__).resolve().parents[2] / 'remotion',
))
FPS = 30


def render(composition_id: str, props: dict, output_path: Path, duration_sec: float = None) -> bool:
    """
    Render a Remotion composition with given props.

    composition_id: 'NumberCounter' | 'LineChart' | 'BarComparison' | 'SplitScreen' | 'TitleCard' | 'MapWithPins'
    props: data to pass to React component (numbers, labels, etc.)
    output_path: where to save mp4
    duration_sec: длина клипа. Передаётся в props как durationSec — composition
      переопределяет durationInFrames через calculateMetadata (см. Root.tsx), поэтому
      анимация тянется на всю длину сцены, а не морозит последний кадр.
    """
    props = dict(props)
    if duration_sec:
        props['durationSec'] = round(float(duration_sec), 3)
    props_json = json.dumps(props, ensure_ascii=False)

    cmd = [
        'npx', '--yes', 'remotion', 'render',
        composition_id,
        str(output_path),
        '--props', props_json,
        '--codec', 'h264',
        '--pixel-format', 'yuv420p',
        '--log', 'error',
    ]
    # Remotion 4 НЕ читает PUPPETEER/REMOTION_CHROME env → без этого качает ~150MB
    # headless-shell в рантайме (таймаут/трафик). Указываем системный chromium явно.
    chrome = os.getenv('REMOTION_CHROME_EXECUTABLE', '/usr/bin/chromium')
    if Path(chrome).exists():
        cmd += ['--browser-executable', chrome, '--disable-web-security']

    try:
        r = subprocess.run(cmd, cwd=REMOTION_DIR, capture_output=True, timeout=300)
        if r.returncode == 0 and output_path.exists() and output_path.stat().st_size > 10000:
            return True
        print(f'Remotion render FAILED for {composition_id}: {r.stderr.decode()[-300:]}')
        return False
    except Exception as e:
        print(f'Remotion EXC: {e}')
        return False


def render_for_scene(scene_data: dict, output_path: Path) -> bool:
    """
    Render the appropriate Remotion composition based on scene classification.
    scene_data: {'type': 'remotion_X', 'remotion_data': {...}, 'duration': N}
    """
    rtype = scene_data.get('type','')
    data = scene_data.get('remotion_data', {})
    duration = scene_data.get('duration', 6)
    
    type_to_comp = {
        'remotion_counter': 'NumberCounter',
        'remotion_chart': 'LineChart',
        'remotion_split': 'SplitScreen',
        'remotion_title': 'TitleCard',
        'remotion_map': 'MapWithPins',
        'remotion_flow': 'FlowConnection',
        'remotion_concept': 'ConceptCard',
        'remotion_stat': 'StatCard',
        'remotion_timeline': 'Timeline',
        'remotion_ranked': 'RankedBars',
        'remotion_table': 'ComparisonTable',
        'remotion_quote': 'QuoteCard',
    }
    # split_kind согласован валидатором: numeric→BarComparison, textual→SplitScreen
    # (раньше различали по isinstance(leftValue) — строковое '17000' молча уходило
    # в безбарный SplitScreen).
    if rtype == 'remotion_split':
        comp = 'BarComparison' if data.get('split_kind') == 'numeric' else 'SplitScreen'
    else:
        comp = type_to_comp.get(rtype)
    
    if not comp:
        return False
    
    return render(comp, data, output_path, duration)


if __name__ == '__main__':
    # Quick test
    import sys, tempfile
    if len(sys.argv) < 2:
        print('Usage: remotion_render.py <comp_id> [props_json] [out.mp4]')
        sys.exit(1)
    comp = sys.argv[1]
    props = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path('/tmp/test_remotion.mp4')
    ok = render(comp, props, out, 5)
    print(f'{"OK" if ok else "FAIL"} {out}')
