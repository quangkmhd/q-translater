"""Bundle the review prototype into one offline HTML file, including system icons."""
from pathlib import Path
import base64
import re

root = Path(__file__).resolve().parent
html = (root / 'dashboard.html').read_text()
css = (root / 'dashboard.css').read_text()
js = (root / 'dashboard.js').read_text()
sources = {}
for path in (root / 'assets/icons').glob('*.svg'):
    sources[path.stem] = 'data:image/svg+xml;base64,' + base64.b64encode(path.read_bytes()).decode()
html = html.replace('<link rel="stylesheet" href="dashboard.css">', '<style>\n' + css + '\n</style>')
html = re.sub(r'src="assets/icons/([\w-]+)\.svg"', lambda m: 'src="' + sources[m[1]] + '"', html)
js = js.replace('const icons = name => `assets/icons/${name}.svg`;', 'const bundledIcons = ' + __import__('json').dumps(sources) + ';\nconst icons = name => bundledIcons[name];')
html = html.replace('<script src="dashboard.js"></script>', '<script>\n' + js + '\n</script>')
(root / 'q-translate-dashboard.html').write_text(html)
print('Built preview/q-translate-dashboard.html (offline, one file).')
