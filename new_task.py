"""Create a task folder: python new_task.py "<slug>" """
import sys, re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
slug = re.sub(r"[^a-z0-9]+", "_", " ".join(sys.argv[1:]).lower()).strip("_")
if not slug:
    sys.exit('usage: python new_task.py "<slug>"')
d = ROOT / "tasks" / f"{date.today():%Y-%m-%d}_{slug}"
d.mkdir(parents=True, exist_ok=False)
(d / "README.md").write_text(
    f"# {slug}\n\n- Requester:\n- Date: {date.today()}\n- Status: open\n\n## Ask\n\n## Notes / Output\n",
    encoding="utf-8")
(d / "run.py").write_text(
    "import sys\nfrom pathlib import Path\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parents[2]))\n"
    "from common.io_utils import read_any, save, INPUT, OUTPUT  # noqa\n\n\n"
    "def main():\n    pass\n\n\nif __name__ == '__main__':\n    main()\n",
    encoding="utf-8")
print(d)
