import os
import re
import sys
import argparse
import ast
from datetime import datetime
from ruamel.yaml import YAML
from ruamel.yaml.parser import ParserError
import yaml
import ast
from io import StringIO

# --- Load configuration ---
def load_config(config_file):
    yaml = YAML()
    with open(config_file, 'r', encoding='utf-8') as f:
        return yaml.load(f)
    
# --- Fix bad headers 
def fix_dangling_heading(content):
    # Fix common pattern: "---# Heading" -> "---\n# Heading"
    return re.sub(r'^---(.)', '---\n\1', content, flags=re.MULTILINE)

def strip_extra_quotes(s):
    if not isinstance(s, str):
        s = str(s)
    return s.strip("'\"").strip("\"'").strip()

def normalize(s):
    return re.sub(r'\s+', ' ', strip_extra_quotes(str(s))).replace("?", "").strip()

def sanitize_list_field(value, title=None):
    if isinstance(value, str):
        value = strip_extra_quotes(value)
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                value = parsed
        except:
            value = [value]

    if isinstance(value, list):
        norm_title = normalize(str(title)) if title else None 

        # Compare first value (as string) to title
        if norm_title and len(value) == 1:
            if normalize(str(value[0])) == norm_title:
                return [norm_title]
            
        cleaned = []
        for item in value:
            item = normalize(item)
            if re.search(r'[\s,:|]', item):
                cleaned.append(f'"{item}"')
            else:
                cleaned.append(item)
        return cleaned

    return [f'"{normalize(value)}"']
 
def clean_malformed_title(raw_title, max_depth=5):
    """
    Cleans malformed YAML title strings that are over-escaped or wrapped in extra quotes.
    Removes outer quotes, unescapes inner quotes and slashes, and stops at safe depth.
    """
    if not isinstance(raw_title, str):
        return raw_title

    s = raw_title.strip()
    last_s = None

    for _ in range(max_depth):
        if s == last_s:
            break
        last_s = s

        # Unescape common escaped patterns
        s = s.replace('\\\\', '\\')      # Double backslashes
        s = s.replace('\\"', '"')        # Escaped double quotes
        s = s.replace("\\'", "'")        # Escaped single quotes

        # Remove wrapping quotes repeatedly
        while (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            s = s[1:-1].strip()

        # Optional: replace repeated quote marks (e.g. ""title"")
        s = re.sub(r'^[\'"]{2,}', '', s)
        s = re.sub(r'[\'"]{2,}$', '', s)

    return s.strip()

def quote_url_like_aliases(frontmatter_raw):
    """
    Detects and rewrites aliases: [http(s)://...] → aliases:\n  - "http(s)://..."
    """
    fixed_lines = []
    for line in frontmatter_raw.splitlines():
        match = re.match(r'^\s*aliases\s*:\s*\[(https?://[^\]]+)\]\s*$', line.strip())
        if match:
            url = match.group(1).strip()
            fixed_lines.append(f'aliases:\n  - "{url}"')
        else:
            fixed_lines.append(line)
    return '\n'.join(fixed_lines)

def quote_url_like_source(frontmatter_raw):
    """
    Detects and rewrites source: [http(s)://...] → aliases:\n  - "http(s)://..."
    """
    fixed_lines = []
    for line in frontmatter_raw.splitlines():
        match = re.match(r'^\s*source\s*:\s*(https?://[^\]]+)\s*$', line.strip())
        if match:
            url = match.group(1).strip()
            fixed_lines.append(f'source: "{url}"')
        else:
            fixed_lines.append(line)
    return '\n'.join(fixed_lines)

def fix_multiline_unquoted_alias_url(frontmatter_raw):
    """
    Fixes broken alias blocks like:
    aliases: [
        https://...]
    Into:
    aliases:
      - "https://..."
    """
    lines = frontmatter_raw.splitlines()
    fixed_lines = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("aliases: [") and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line.startswith("http://") or next_line.startswith("https://"):
                url = next_line.rstrip(']')  # trim closing bracket if present
                fixed_lines.append("aliases:")
                fixed_lines.append(f'  - "{url}"')
                i += 2  # skip both lines
                continue
        fixed_lines.append(lines[i])
        i += 1

    return '\n'.join(fixed_lines)

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

def extract_title_from_raw_frontmatter(frontmatter_text):
    """
    Attempts to extract and clean a title from raw frontmatter text.
    """
    match = re.search(r'^title:\s*(.+)$', frontmatter_text, re.MULTILINE)
    if match:
        raw_title = match.group(1).strip()
        return clean_malformed_title(raw_title)
    return None

def normalize_for_compare(s):
    return re.sub(r'\s+', ' ', str(s).strip().strip('"').strip("'").replace("[", "").replace("]", "")).lower()

def attempt_fix_broken_frontmatter(frontmatter_text, title=None):
    fixed = frontmatter_text

    # 🔧 Step 1: Fix missing commas between adjacent quoted strings
    fixed = re.sub(r'(".*?")\s+(".*?")', r'\1, \2', fixed)

    # 🔧 Step 2: Handle aliases (title heuristic + rescue from inline format) 
    title = extract_title_from_raw_frontmatter(frontmatter_text)
    title = title.replace('"', '\\"').replace(' - ', ' ').replace('|', '').replace("[", "").replace("]", "")
    fixed = re.sub(
        r'title:\s*(.+)',
        f'title: "{title}"',
        fixed
    )

    alias_match = re.search(r'aliases:\s*\[(.*?)\]', fixed) 

    if alias_match:
        raw_aliases = alias_match.group(1) 
        raw_aliases = raw_aliases.replace('"', '\\"').replace(' - ', ' ').replace('|', '').replace("[", "").replace("]", "")
        # print(normalize_for_compare(raw_aliases)) 
        # print(normalize_for_compare(title))

        if title and normalize_for_compare(title) in normalize_for_compare(raw_aliases):
            cleaned = normalize_for_compare(title)
            fixed = re.sub(
                r'aliases:\s*\[(.*?)\]',
                f'aliases:\n  - "{cleaned}"',
                fixed, re.MULTILINE
            )
        else:
            # Treat as possibly broken list → wrap in block-style anyway
            items = [x.strip().strip('"').strip("'") for x in re.split(r',\s*', raw_aliases)]
            cleaned = '\n  - '.join([f'"{i}"' if re.search(r'[\s,:|]', i) else i for i in items])
            fixed = re.sub(
                r'aliases:\s*\[(.*?)\]',
                f'aliases:\n  - {cleaned}',
                fixed
            )

    # 🔧 Step 3: Fix broken inline tags
    tag_match = re.search(r'tags:\s*\[(.*?)\]', fixed)

    if tag_match:
        tag_items = [t.strip().strip('"').strip("'").replace(" ","_").replace("-","_") for t in re.split(r',\s*', tag_match.group(1))]
        cleaned = '\n  - '.join([f'"{t}"' if re.search(r'[\s,:|]', t) else t for t in tag_items])
        fixed = re.sub(
            r'tags:\s*\[.*?\]',
            f'tags:\n  - {cleaned}',
            fixed
        )

    # print(fixed)
    return fixed

def fix_frontmatter(content, filename, required_fields, default_tag):
    def extract_frontmatter_block(content):
        lines = content.splitlines()
        if len(lines) < 3 or lines[0].strip() != "---":
            return None, None, None
        try:
            end_index = lines[1:].index("---") + 1
        except ValueError:
            return None, None, None
        frontmatter = "\n".join(lines[1:end_index])
        rest = "\n".join(lines[end_index + 1:])
        return frontmatter, end_index, rest

    frontmatter, end_index, body = extract_frontmatter_block(content)
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False

    #if os.path.splitext(os.path.basename(filename))[0] == "authors-at-google-george-dyson-turing-s-cathedral-youtube":
    #    print(frontmatter)

    if frontmatter is None:
        data = {}
        if "title" in required_fields:
            data["title"] = os.path.splitext(os.path.basename(filename))[0]
        if "created" in required_fields:
            data["created"] = datetime.fromtimestamp(os.path.getctime(filename)).isoformat()
        if "tags" in required_fields:
            data["tags"] = [default_tag]
        stream = StringIO()
        yaml.dump(data, stream)
        new_yaml = stream.getvalue()
        return f"---\n{new_yaml}---\n{content.lstrip()}", "Inserted new frontmatter"

    try:
        data = yaml.load(frontmatter) or {}
    except Exception as e:
        # First fix attempt
        print(f"⚠️ Parse failed. Attempting rescue for {filename}")
        frontmatter_fixed = attempt_fix_broken_frontmatter(frontmatter, title="")
        try:
            data = yaml.load(frontmatter_fixed)
            modified = True  # We changed something
        except Exception as e2:
            print(f"❌ Still invalid after fix: {str(e2).splitlines()[0]}")
            return None, f"❌ Still invalid after fix: {str(e2).splitlines()[0]}"

    modified = False
    title_value = data.get("title")

    for key in ["aliases", "tags", "topics", "categories"]:
        if key in data:
            cleaned = sanitize_list_field(data[key], title=title_value if key == "aliases" else None)
            if cleaned != data[key]:
                data[key] = cleaned
                modified = True

    if 'tags' in frontmatter:
        original_tags = data['tags']
        cleaned_tags = clean_tags(original_tags)
        if cleaned_tags != original_tags:
            data['tags'] = cleaned_tags
            modified = True

    if "title" in required_fields and "title" not in data:
        data["title"] = os.path.splitext(os.path.basename(filename))[0]
        modified = True
    if "created" in required_fields and "created" not in data:
        data["created"] = datetime.fromtimestamp(os.path.getctime(filename)).isoformat()
        modified = True
    if "tags" in required_fields and "tags" not in data:
        data["tags"] = [default_tag]
        modified = True

    if modified:
        stream = StringIO()
        yaml.dump(data, stream)
        new_yaml = stream.getvalue()
        return f"---\n{new_yaml}---\n{body}", "Fixed existing frontmatter"
    else:
        return None, "Valid and unmodified"



# --- Walk vault ---
def process_vault(config):
    vault_path = config['vault_path']
    required_fields = config['required_fields']
    default_tag = config['default_tag']

    for root, _, files in os.walk(vault_path):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            full_path = os.path.join(root, fname)
            with open(full_path, encoding="utf-8") as f:
                original_content = f.read()

            # Step 1: Fix common frontmatter-breaker like "---#Heading"
            preprocessed_content = fix_dangling_heading(original_content)
            preprocessed_content = fix_multiline_unquoted_alias_url(preprocessed_content)
            preprocessed_content = quote_url_like_aliases(preprocessed_content)
            preprocessed_content = quote_url_like_source(preprocessed_content)
            heading_fixed = (preprocessed_content != original_content)

            # Step 2: Fix or insert frontmatter
            fixed_content, status = fix_frontmatter(
                preprocessed_content, full_path, required_fields, default_tag
            )

            # Determine what to write
            if fixed_content:
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(fixed_content)
                print(f"✅ Fixed frontmatter: {full_path}")
            elif heading_fixed:
                # Only the heading was fixed; save the cleaned version
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(preprocessed_content)
                print(f"🔧 Fixed heading only: {full_path}")
            # else:
                # print(f"ℹ️ Skipped ({status}): {full_path}")


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
