import os
from pathlib import Path

def process_file(path: Path):
    if not path.is_file():
        return
    if path.suffix not in [".json", ".sh", ".py", ".md"]:
        return
    try:
        content = path.read_text(encoding="utf-8")
        if ".claude" in content:
            new_content = content.replace(".claude", ".agents")
            path.write_text(new_content, encoding="utf-8")
            print(f"Updated {path}")
    except Exception as e:
        print(f"Skipping {path}: {e}")

def main():
    root = Path("/home/vytcepas/projects/project_init")
    
    for folder in ["plugins", ".agents-plugin"]:
        for root_dir, dirs, files in os.walk(root / folder):
            for file in files:
                process_file(Path(root_dir) / file)

if __name__ == "__main__":
    main()
