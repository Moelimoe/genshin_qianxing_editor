import sys
from pathlib import Path

# Add project root and app directory to sys.path
PROJECT_ROOT = Path('.').resolve()
APP_DIR = PROJECT_ROOT / "app"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))

print('Testing imports...')
try:
    from runtime.engine.graph_prelude_server import GameRuntime
    print('✅ Successfully imported GameRuntime from runtime.engine.graph_prelude_server')
    print('Import path is correct!')
except ImportError as e:
    print(f'❌ Import failed: {e}')
    print('Trying alternative import path...')
    try:
        from assets.资源库.节点图.server import _prelude
        print('✅ Successfully imported from assets.资源库.节点图.server')
        print('Alternative import path works!')
    except ImportError as e2:
        print(f'❌ Alternative import also failed: {e2}')

print('\nCurrent sys.path:')
for i, path in enumerate(sys.path[:5]):
    print(f'{i+1}. {path}')