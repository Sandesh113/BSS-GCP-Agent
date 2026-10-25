"""Pull each scene's narration (say:"...") from the walkthrough page, in order."""
import json
import re
import sys
from pathlib import Path

html = Path(sys.argv[1]).read_text(encoding="utf-8")
says = [json.loads('"' + s + '"') for s in re.findall(r'say:"((?:[^"\\]|\\.)*)"', html)]
Path(sys.argv[2]).write_text(json.dumps(says, indent=1, ensure_ascii=False), encoding="utf-8")
print(len(says), "scenes,", sum(len(s) for s in says), "characters")
for i, s in enumerate(says, 1):
    print(i, s[:80])
