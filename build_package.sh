#!/bin/bash

# Mem0 Dify Plugin Package Builder
# This script creates a .difypkg file for the Mem0 plugin

set -e

# Get plugin name and version from manifest.yaml
if [ ! -f "manifest.yaml" ]; then
    echo "❌ Error: manifest.yaml not found!"
    exit 1
fi

PLUGIN_NAME=$(grep "^name:" manifest.yaml | sed 's/^name:[[:space:]]*//' | tr -d '"' | tr -d "'")
VERSION=$(grep "^version:" manifest.yaml | sed 's/^version:[[:space:]]*//' | tr -d '"' | tr -d "'")

if [ -z "$PLUGIN_NAME" ] || [ -z "$VERSION" ]; then
    echo "❌ Error: Failed to extract plugin name or version from manifest.yaml"
    exit 1
fi

OUTPUT_FILE="${PLUGIN_NAME}-${VERSION}.difypkg"
TEMP_DIR="temp_package"

echo "🚀 Building Mem0 Dify Plugin v${VERSION}..."
echo "   Plugin: ${PLUGIN_NAME}"
echo "   Version: ${VERSION}"
echo ""

# Clean up previous builds
rm -rf "$TEMP_DIR" "$OUTPUT_FILE"
mkdir -p "$TEMP_DIR"

# Copy essential files
echo "📦 Copying plugin files..."

# Core files (required)
cp manifest.yaml "$TEMP_DIR/"
cp main.py "$TEMP_DIR/"
cp requirements.txt "$TEMP_DIR/"
cp PRIVACY.md "$TEMP_DIR/"
cp README.md "$TEMP_DIR/"
cp CHANGELOG.md "$TEMP_DIR/"
cp .difyignore "$TEMP_DIR/"

# Copy __init__.py if it exists
if [ -f "__init__.py" ]; then
    cp __init__.py "$TEMP_DIR/"
fi

# Copy LICENSE if it exists
if [ -f "LICENSE" ]; then
    cp LICENSE "$TEMP_DIR/"
fi

# Copy provider directory
if [ -d "provider" ]; then
    cp -r provider "$TEMP_DIR/"
else
    echo "⚠️  Warning: provider directory not found!"
fi

# Copy tools directory
if [ -d "tools" ]; then
    cp -r tools "$TEMP_DIR/"
else
    echo "⚠️  Warning: tools directory not found!"
fi

# Copy utils directory
if [ -d "utils" ]; then
    cp -r utils "$TEMP_DIR/"
else
    echo "⚠️  Warning: utils directory not found!"
fi

# Copy assets directory
if [ -d "_assets" ]; then
    cp -r _assets "$TEMP_DIR/"
else
    echo "⚠️  Warning: _assets directory not found!"
fi

# Remove any Python cache files and other unwanted files
echo "🧹 Cleaning up..."
find "$TEMP_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$TEMP_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$TEMP_DIR" -type f -name "*.pyo" -delete 2>/dev/null || true
find "$TEMP_DIR" -type f -name ".DS_Store" -delete 2>/dev/null || true
find "$TEMP_DIR" -type f -name "*.swp" -delete 2>/dev/null || true
find "$TEMP_DIR" -type f -name "*.swo" -delete 2>/dev/null || true
find "$TEMP_DIR" -type f -name "*~" -delete 2>/dev/null || true

# Create the .difypkg file (it's just a zip file)
echo "📦 Creating ${OUTPUT_FILE}..."
cd "$TEMP_DIR"
# Use -D to not create directory entries in zip
zip -r -D "../${OUTPUT_FILE}" . -q
cd ..

# Clean up temp directory
rm -rf "$TEMP_DIR"

# Get file size
FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)

echo ""
echo "✅ Package created successfully!"
echo ""
echo "📄 Package Details:"
echo "   Name: ${OUTPUT_FILE}"
echo "   Size: ${FILE_SIZE}"
echo "   Location: $(pwd)/${OUTPUT_FILE}"
echo ""
echo "🎉 You can now upload this package to Dify!"
