#!/bin/bash
cd /home/ec2-user/www/work

# Root md files (excluding README.md)
root_files=$(find . -maxdepth 1 -name "*.md" ! -name "README.md" | sed 's|^\./||' | sort | jq -R . | jq -s .)

# Build dirs object (recursive — includes subdirs like original/)
dirs="{}"
for d in $(find . -mindepth 1 -maxdepth 1 -type d ! -name '.git' | sed 's|^\./||' | sort); do
  # Collect all md files recursively, with relative path from project dir
  d_files=$(find "$d" -name "*.md" ! -name "README.md" | sed "s|^${d}/||" | sort | jq -R . | jq -s .)
  dirs=$(echo "$dirs" | jq --arg k "$d" --argjson v "$d_files" '. + {($k): {"files": $v}}')
done

jq -n --argjson files "$root_files" --argjson dirs "$dirs" '{files: $files, dirs: $dirs}' > files.json
