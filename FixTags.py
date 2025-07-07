import os
import re
import argparse
import yaml
import sys
from ruamel.yaml import YAML
from ruamel.yaml.parser import ParserError


# --- Load configuration ---
def load_config(config_file):
    yaml = YAML() 
    with open(config_file, 'r', encoding='utf-8') as f:
        return yaml.load(f)
    
def sanitize_tag(tag):
    """Replace spaces with underscores, remove invalid characters, and lowercase."""
    if isinstance(tag, str):
        tag = tag.strip().replace(' ', '_')
        tag = tag.strip().replace('-', '_')
        tag = re.sub(r'[^\w\-]', '', tag)
        return tag.lower()
    else:
        return False

def clean_tags(raw_tags):
    """Convert comma-separated strings to list, clean, deduplicate, and sanitize tags."""
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(',') if t.strip()]
    elif isinstance(raw_tags, list):
        tags = raw_tags
    else:
        return []

    cleaned = set()
    for tag in tags:
        sanitized = sanitize_tag(tag)
        if sanitized:
            cleaned.add(sanitized)

    return sorted(cleaned)

def process_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Match YAML frontmatter
    match = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
    if not match:
        return

    yaml_str, body = match.groups()
    try:
        frontmatter = yaml.safe_load(yaml_str)
    except yaml.YAMLError:
        return

    if 'tags' in frontmatter:
        original_tags = frontmatter['tags']
        frontmatter['tags'] = clean_tags(original_tags)

        new_yaml = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False, width=float("inf"))
        new_content = f"---\n{new_yaml}---\n{body}"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Normalized and cleaned tags in: {file_path}")

def process_vault(config):
    vault_path = config['vault_path'] 

    for root, dirs, files in os.walk(vault_path):
        for name in files:
            if name.endswith('.md'):
                full_path = os.path.join(root, name)
                process_file(full_path)

# --- Entry point ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix YAML frontmatter in Obsidian notes.")
    parser.add_argument("--config", default="_config.yaml", help="Path to YAML config file")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        process_vault(config)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
