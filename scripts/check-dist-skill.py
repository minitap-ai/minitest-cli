"""Fail unless the built wheel and sdist both carry the agent skill and its reference index.

Run after `uv build`. The skill ships inside the wheel so it always matches the CLI;
a build that silently drops it would leave `minitest skill` and `minitest upgrade`
without anything to install.
"""

import glob
import sys
import tarfile
import zipfile

wheel = zipfile.ZipFile(glob.glob("dist/*.whl")[0]).namelist()
sdist = tarfile.open(glob.glob("dist/*.tar.gz")[0]).getnames()

checks = {
    "wheel": (
        wheel,
        (
            "minitest_cli/_skills/minitest-cli/SKILL.md",
            "_skills/minitest-cli/reference/index.json",
        ),
    ),
    "sdist": (sdist, ("skills/minitest-cli/SKILL.md", "skills/minitest-cli/reference/index.json")),
}
failed = False
for label, (names, fragments) in checks.items():
    for fragment in fragments:
        if not any(fragment in name for name in names):
            print(f"::error::{label} is missing the agent skill ({fragment})")
            failed = True
if failed:
    sys.exit(1)
print("Agent skill is in the wheel and the sdist")
