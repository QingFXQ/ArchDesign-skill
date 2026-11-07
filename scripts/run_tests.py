"""Run every maintained test suite; historical project execution scripts are inert data."""
from pathlib import Path
import os
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
skill=root/'skills/architecture-design-workflow'
suites=[skill/'scripts',skill/'assets/knowledge/architecture-case-rag/scripts',skill/'scripts/revit-mcp/scripts',root/'tests']
failed=False
for suite in suites:
    result=subprocess.run([sys.executable,'-X','utf8','-m','unittest','discover','-s',str(suite),'-p','test_*.py','-v'],cwd=root,env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8'))
    failed |= result.returncode != 0
raise SystemExit(1 if failed else 0)
