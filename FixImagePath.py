import os
import re
from pathlib import Path

# Set the path to your Obsidian vault
vault_path = Path("E:\\Documents\\Local Files\\_Wiki\\HomeNotes\\SharedVault")  # <-- Update this path

# Regex to find image markdown links: ![alt text](path)
image_pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

# Track files that were modified
fixed_files = []

def fix_image_paths_in_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    updated = False

    def replace_path(match):
        nonlocal updated
        alt_text, path = match.groups()
        if "\\" in path:
            fixed_path = path.replace("\\", "/")
            updated = True
            return f"![{alt_text}]({fixed_path})"
        return match.group(0)

    new_content = image_pattern.sub(replace_path, content)

    if updated:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        fixed_files.append(str(file_path.relative_to(vault_path)))

# Recursively process all .md files in the vault
for root, dirs, files in os.walk(vault_path):
    for file in files:
        if file.endswith('.md'):
            fix_image_paths_in_file(Path(root) / file)

# Report results
print("✅ Fixed files:")
for file in fixed_files:
    print(" -", file)

if not fixed_files:
    print("No image paths needed fixing.")
