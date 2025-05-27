import os
import re

def remove_comments_from_line(line):
    """Remove inline comments while preserving strings."""
    in_string = False
    escaped = False
    quote_char = ''
    result = ''

    for i, char in enumerate(line):
        if char == '\\' and not escaped:
            escaped = True
            result += char
            continue

        if char in ('"', "'") and not escaped:
            if not in_string:
                in_string = True
                quote_char = char
            elif quote_char == char:
                in_string = False
        elif char == '#' and not in_string:
            return result.rstrip()
        result += char
        escaped = False

    return result.rstrip()

def remove_comments_from_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    in_multiline_string = False
    new_lines = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            new_lines.append(line)
            continue

        if not in_multiline_string:
            if stripped.startswith(('"""', "'''")) and stripped.count(stripped[:3]) == 1:
                in_multiline_string = True
                new_lines.append(line)
                continue
            elif stripped.startswith('#'):
                continue
            else:
                new_line = remove_comments_from_line(line)
                if new_line.strip():
                    new_lines.append(new_line + '\n')
        else:
            new_lines.append(line)
            if stripped.endswith(('"""', "'''")):
                in_multiline_string = False

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

def remove_comments_from_project(root_dir='.'):
    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith('.py'):
                full_path = os.path.join(root, file)
                print(f"Processing: {full_path}")
                try:
                    remove_comments_from_file(full_path)
                except Exception as e:
                    print(f"Failed to process {full_path}: {e}")

if __name__ == '__main__':
    remove_comments_from_project('.')
