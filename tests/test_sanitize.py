"""Tests for sanitize() text cleaning."""

from speakly.sanitize import sanitize


def test_bare_urls_removed():
    assert sanitize("Visit https://example.com/path?q=1 for info") == "Visit  for info"


def test_www_urls_removed():
    assert sanitize("Check www.example.com now") == "Check  now"


def test_markdown_links_keep_text():
    assert sanitize("[click here](https://example.com)") == "click here"


def test_markdown_images_removed():
    assert sanitize("![alt text](https://img.png)") == ""


def test_bold_stripped():
    assert sanitize("**important**") == "important"


def test_italic_star_stripped():
    assert sanitize("*emphasis*") == "emphasis"


def test_italic_underscore_stripped():
    assert sanitize("_emphasis_") == "emphasis"


def test_underscore_in_words_preserved():
    assert sanitize("variable_name") == "variable_name"


def test_strikethrough_stripped():
    assert sanitize("~~deleted~~") == "deleted"


def test_headings_stripped():
    assert sanitize("## Title") == "Title"
    assert sanitize("### Subtitle") == "Subtitle"


def test_horizontal_rules_removed():
    assert sanitize("---") == ""
    assert sanitize("***") == ""


def test_code_fences_removed_content_kept():
    result = sanitize("```python\nprint('hi')\n```")
    assert "print('hi')" in result
    assert "```" not in result


def test_inline_code_stripped():
    assert sanitize("run `grep` now") == "run grep now"


def test_bullet_markers_stripped():
    assert sanitize("- item one") == "item one"
    assert sanitize("1. item one") == "item one"


def test_blockquotes_stripped():
    assert sanitize("> quoted text") == "quoted text"


def test_blank_lines_collapsed():
    assert sanitize("a\n\n\n\nb") == "a\n\nb"


def test_combined_input():
    text = "## Hello\n\n**Bold** and [link](https://x.com)\n\n- item"
    result = sanitize(text)
    assert "##" not in result
    assert "**" not in result
    assert "https://x.com" not in result
    assert "Hello" in result
    assert "Bold" in result
    assert "link" in result
    assert "item" in result


def test_url_only_input_becomes_empty():
    """Input that's only a URL should sanitize to empty string."""
    assert sanitize("https://example.com") == ""


def test_image_only_input_becomes_empty():
    assert sanitize("![photo](https://img.jpg)") == ""
