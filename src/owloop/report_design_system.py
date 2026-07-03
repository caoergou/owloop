"""Design tokens and component styles for owloop HTML reports.

This module centralizes the visual language of `owloop report` so that:
1. AI-generated content can be injected without worrying about styling.
2. Reports render consistently offline (inline CSS) or enhanced (Tailwind CDN).
3. The brand (Ollie the owl, night/amber palette) is preserved across surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColorTokens:
    """Semantic color tokens from .github/BRAND.md."""

    night: str = "#0b1026"
    night_landing: str = "#080c1d"
    night_card: str = "#121a2e"
    dim_blue: str = "#3a4270"
    amber: str = "#d4a025"
    amber_bright: str = "#f0c563"
    moon_white: str = "#f2ecd8"
    moon_dim: str = "#8890b3"
    success: str = "#8fd19e"
    danger: str = "#e0777d"
    gray: str = "#8890b3"
    cyan: str = "#8fb8de"


@dataclass(frozen=True)
class FontTokens:
    """Typography tokens from .github/BRAND.md."""

    display: str = '"Cinzel Decorative", Georgia, serif'
    sans: str = 'Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
    tagline: str = 'Caveat, "Brush Script MT", cursive'
    mono: str = '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'
    base_size: str = "16px"
    line_height: str = "1.6"


@dataclass(frozen=True)
class SpacingTokens:
    """4/8 pt spacing scale, borrowed from ui-ux-pro-max conventions."""

    xs: str = "0.25rem"   # 4px
    sm: str = "0.5rem"    # 8px
    md: str = "1rem"      # 16px
    lg: str = "1.5rem"    # 24px
    xl: str = "2rem"      # 32px
    xxl: str = "3rem"     # 48px


def google_fonts_link() -> str:
    """Return the <link> tag for Google Fonts used by the brand."""
    families = "family=Cinzel+Decorative:wght@400;700&family=Caveat:wght@400;700&family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400;600"
    return f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{families}&display=swap">'


def css_variables(colors: ColorTokens | None = None, fonts: FontTokens | None = None) -> str:
    """Return the CSS :root block with all design tokens."""
    c = colors or ColorTokens()
    f = fonts or FontTokens()
    return f"""
:root {{
  --owl-night: {c.night};
  --owl-night-landing: {c.night_landing};
  --owl-night-card: {c.night_card};
  --owl-dim-blue: {c.dim_blue};
  --owl-amber: {c.amber};
  --owl-amber-bright: {c.amber_bright};
  --owl-moon: {c.moon_white};
  --owl-moon-dim: {c.moon_dim};
  --owl-success: {c.success};
  --owl-danger: {c.danger};
  --owl-gray: {c.gray};
  --owl-cyan: {c.cyan};
  --owl-font-display: {f.display};
  --owl-font-sans: {f.sans};
  --owl-font-tagline: {f.tagline};
  --owl-font-mono: {f.mono};
  --owl-base-size: {f.base_size};
  --owl-line-height: {f.line_height};
}}
"""


def base_styles() -> str:
    """Return the complete inline stylesheet for a self-contained report."""
    return f"""
{css_variables()}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  font-family: var(--owl-font-sans);
  font-size: var(--owl-base-size);
  line-height: var(--owl-line-height);
  background: var(--owl-night);
  color: var(--owl-moon);
  margin: 0;
  padding: 0;
}}
.container {{
  max-width: 960px;
  margin: 0 auto;
  padding: 2rem 1rem;
}}
header {{
  text-align: center;
  border-bottom: 2px solid var(--owl-amber);
  padding-bottom: 1.5rem;
  margin-bottom: 2rem;
}}
.owl {{
  color: var(--owl-amber);
  font-size: 0.85rem;
  line-height: 1.1;
  white-space: pre;
  overflow-x: auto;
}}
h1, h2, h3 {{
  color: var(--owl-amber);
  font-family: var(--owl-font-sans);
  margin-top: 0;
}}
h1 {{ font-size: 2rem; margin-bottom: 0.25rem; }}
h2 {{ font-size: 1.4rem; margin-top: 2rem; border-bottom: 1px solid var(--owl-dim-blue); padding-bottom: 0.3rem; }}
h3 {{ font-size: 1.1rem; margin-bottom: 0.5rem; }}
p {{ margin: 0.5rem 0; }}
.meta {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin: 2rem 0;
}}
.card {{
  background: var(--owl-night-card);
  border: 1px solid var(--owl-dim-blue);
  border-radius: 8px;
  padding: 1rem;
  min-width: 0;
}}
.card h3 {{ margin-top: 0; }}
.badge {{
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}}
.badge-success {{ background: rgba(143, 209, 158, 0.15); color: var(--owl-success); }}
.badge-danger {{ background: rgba(224, 119, 125, 0.15); color: var(--owl-danger); }}
.badge-info {{ background: rgba(126, 184, 218, 0.15); color: var(--owl-cyan); }}
.insight {{
  background: var(--owl-night-card);
  border-left: 4px solid var(--owl-amber);
  padding: 1rem 1.25rem;
  border-radius: 0 8px 8px 0;
  margin: 1rem 0;
}}
.insight h4 {{
  color: var(--owl-amber-bright);
  margin: 0 0 0.5rem 0;
  font-family: var(--owl-font-sans);
}}
.insight p {{ margin: 0.25rem 0; }}
table {{
  width: 100%;
  border-collapse: collapse;
  margin-top: 1rem;
  table-layout: auto;
}}
th, td {{
  text-align: left;
  padding: 0.6rem;
  border-bottom: 1px solid var(--owl-dim-blue);
  vertical-align: top;
  min-width: 0;
}}
th {{ color: var(--owl-amber); white-space: nowrap; }}
td {{ word-break: break-word; }}
td code {{ word-break: break-all; }}
.stats {{ color: var(--owl-success); font-weight: 600; }}
.del {{ color: var(--owl-danger); font-weight: 600; }}
footer {{
  margin-top: 3rem;
  text-align: center;
  color: var(--owl-moon-dim);
  font-size: 0.85rem;
}}
code {{
  background: rgba(255, 255, 255, 0.08);
  padding: 0.15rem 0.35rem;
  border-radius: 4px;
  font-family: var(--owl-font-mono);
}}
.empty {{
  color: var(--owl-moon-dim);
  font-style: italic;
}}
@media (max-width: 600px) {{
  .container {{ padding: 1rem 0.75rem; }}
  h1 {{ font-size: 1.5rem; }}
  .meta {{ grid-template-columns: 1fr; }}
  table {{ font-size: 0.85rem; }}
  th, td {{ padding: 0.4rem; }}
}}
"""


def tailwind_cdn() -> str:
    """Return the Tailwind CSS v4 + DaisyUI CDN snippet for enhanced reports."""
    return """
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://cdn.jsdelivr.net/npm/daisyui@4/dist/full.min.css" rel="stylesheet" type="text/css" />
<script>
  tailwind.config = {
    theme: {
      extend: {
        colors: {
          'owl-night': '#0b1026',
          'owl-card': '#121a2e',
          'owl-dim': '#3a4270',
          'owl-amber': '#d4a025',
          'owl-amber-bright': '#f0c563',
          'owl-moon': '#f2ecd8',
          'owl-success': '#8fd19e',
          'owl-danger': '#e0777d',
          'owl-gray': '#8890b3',
          'owl-cyan': '#8fb8de',
        },
        fontFamily: {
          display: ['"Cinzel Decorative"', 'Georgia', 'serif'],
          sans: ['Inter', 'system-ui', 'sans-serif'],
          tagline: ['Caveat', 'cursive'],
          mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
        }
      }
    }
  }
</script>
"""
