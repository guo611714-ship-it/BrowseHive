---
name: markitdown
description: "Convert files (PDF/Word/Excel/PPT/HTML/images/audio/video) to Markdown using Microsoft MarkItDown. For LLM text analysis pipelines."
user_invocable: true
---

# MarkItDown — File to Markdown Converter

Microsoft's lightweight Python tool for converting files to Markdown. Ideal for feeding documents into LLM text analysis pipelines.

**Repo:** https://github.com/microsoft/markitdown (134K+ stars)
**Docs:** https://deepwiki.com/microsoft/markitdown

## Supported Formats

| Format | Extensions | Notes |
|--------|-----------|-------|
| PDF | .pdf | Layout preserved, tables supported |
| Word | .docx | Headings, lists, tables, links |
| PowerPoint | .pptx | Slide structure preserved |
| Excel | .xlsx, .xls | Tables converted to Markdown |
| Images | .jpg, .png, .gif, etc. | EXIF metadata + OCR |
| Audio | .wav, .mp3 | EXIF + speech transcription |
| HTML | .html, .htm | Structure preserved |
| Text | .csv, .json, .xml | Direct conversion |
| ZIP | .zip | Iterates over contents |
| YouTube | URLs | Video transcription |
| EPUB | .epub | E-book content |

## Installation

```bash
# Full install (all formats)
pip install 'markitdown[all]'

# Selective install
pip install 'markitdown[pdf,docx,pptx,xlsx]'
```

## CLI Usage

```bash
# Basic conversion
markitdown path-to-file.pdf

# Output to file
markitdown path-to-file.pdf -o document.md

# Pipe input
cat file.pdf | markitdown

# With plugins
markitdown --use-plugins path-to-file.pdf
markitdown --list-plugins

# Azure Document Intelligence
markitdown file.pdf -d -e "<endpoint>"

# Azure Content Understanding
markitdown file.pdf --use-cu --cu-endpoint "<endpoint>"
```

## Python API

### Basic

```python
from markitdown import MarkItDown

md = MarkItDown()
result = md.convert("document.pdf")
print(result.text_content)
```

### With LLM (image descriptions)

```python
from markitdown import MarkItDown
from openai import OpenAI

client = OpenAI()
md = MarkItDown(llm_client=client, llm_model="gpt-4o")
result = md.convert("image.jpg")
print(result.text_content)
```

### With Plugins

```python
md = MarkItDown(enable_plugins=True)
result = md.convert("file.pdf")
```

### Azure Document Intelligence

```python
md = MarkItDown(docintel_endpoint="<endpoint>")
result = md.convert("scanned.pdf")
```

### Azure Content Understanding

```python
md = MarkItDown(cu_endpoint="<endpoint>")
result = md.convert("report.pdf")  # auto-selects analyzer
print(result.markdown)  # includes YAML front matter with fields
```

### Narrow APIs (Security)

```python
# Local files only (most restrictive)
md.convert_local("file.pdf")

# From stream
md.convert_stream(file_obj, file_extension=".pdf")

# From HTTP response
import requests
resp = requests.get("https://example.com/doc.pdf")
md.convert_response(resp, file_extension=".pdf")
```

## Plugins

```bash
# List installed plugins
markitdown --list-plugins

# Enable plugins
markitdown --use-plugins file.pdf
```

Search GitHub for `#markitdown-plugin` to find community plugins.

### markitdown-ocr Plugin

Adds OCR support for embedded images in PDF/DOCX/PPTX/XLSX using LLM Vision.

```bash
pip install markitdown-ocr openai
```

```python
from markitdown import MarkItDown
from openai import OpenAI

md = MarkItDown(
    enable_plugins=True,
    llm_client=OpenAI(),
    llm_model="gpt-4o"
)
result = md.convert("scanned.pdf")
```

## Docker

```bash
docker build -t markitdown:latest .
docker run --rm -i markitdown:latest < file.pdf > output.md
```

## When to Use MarkItDown vs Alternatives

| Scenario | Tool |
|----------|------|
| Feed docs to LLM for analysis | MarkItDown |
| High-fidelity human reading | pandoc / native apps |
| OCR from scanned PDFs | MarkItDown + OCR plugin |
| Office doc editing | word-document-processor skill |
| Quick text extraction | MarkItDown CLI |

## Security Notes

- MarkItDown runs with current process privileges
- Sanitize untrusted inputs in server-side applications
- Prefer narrow APIs (`convert_local`, `convert_stream`) over `convert()` when possible
- Restrict file paths and URI schemes for untrusted inputs

## Python Version

Requires Python 3.10+. Use virtual environment recommended.
