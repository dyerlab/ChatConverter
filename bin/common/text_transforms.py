"""
Shared text transformation utilities for converting chat exports to Obsidian markdown.
Handles emoji removal, math symbol conversion, and LaTeX formatting.
"""

import re

# Math symbol replacements (Unicode → LaTeX wrapped in $...$)
MATH_REPLACEMENTS = {
    # Summation and products
    '∑': r'$\sum$', '∏': r'$\prod$', '∐': r'$\coprod$',
    # Integrals
    '∫': r'$\int$', '∬': r'$\iint$', '∭': r'$\iiint$', '∮': r'$\oint$',
    # Greek letters (lowercase)
    'α': r'$\alpha$', 'β': r'$\beta$', 'γ': r'$\gamma$', 'δ': r'$\delta$',
    'ε': r'$\epsilon$', 'ζ': r'$\zeta$', 'η': r'$\eta$', 'θ': r'$\theta$',
    'ι': r'$\iota$', 'κ': r'$\kappa$', 'λ': r'$\lambda$', 'μ': r'$\mu$',
    'ν': r'$\nu$', 'ξ': r'$\xi$', 'π': r'$\pi$', 'ρ': r'$\rho$',
    'σ': r'$\sigma$', 'τ': r'$\tau$', 'υ': r'$\upsilon$', 'φ': r'$\phi$',
    'χ': r'$\chi$', 'ψ': r'$\psi$', 'ω': r'$\omega$',
    # Greek letters (uppercase)
    'Γ': r'$\Gamma$', 'Δ': r'$\Delta$', 'Θ': r'$\Theta$', 'Λ': r'$\Lambda$',
    'Ξ': r'$\Xi$', 'Π': r'$\Pi$', 'Σ': r'$\Sigma$', 'Φ': r'$\Phi$',
    'Ψ': r'$\Psi$', 'Ω': r'$\Omega$',
    # Operators
    '±': r'$\pm$', '∓': r'$\mp$', '×': r'$\times$', '÷': r'$\div$',
    '·': r'$\cdot$', '∘': r'$\circ$', '⊗': r'$\otimes$', '⊕': r'$\oplus$',
    '√': r'$\sqrt{}$', '∞': r'$\infty$', '∂': r'$\partial$', '∇': r'$\nabla$',
    # Relations
    '≈': r'$\approx$', '≠': r'$\neq$', '≤': r'$\leq$', '≥': r'$\geq$',
    '≪': r'$\ll$', '≫': r'$\gg$', '∝': r'$\propto$', '≡': r'$\equiv$',
    '∼': r'$\sim$', '≃': r'$\simeq$', '≅': r'$\cong$',
    # Set theory
    '∈': r'$\in$', '∉': r'$\notin$', '⊂': r'$\subset$', '⊃': r'$\supset$',
    '⊆': r'$\subseteq$', '⊇': r'$\supseteq$', '∪': r'$\cup$', '∩': r'$\cap$',
    '∅': r'$\emptyset$', '∀': r'$\forall$', '∃': r'$\exists$', '∄': r'$\nexists$',
    # Arrows
    '→': r'$\rightarrow$', '←': r'$\leftarrow$', '↔': r'$\leftrightarrow$',
    '⇒': r'$\Rightarrow$', '⇐': r'$\Leftarrow$', '⇔': r'$\Leftrightarrow$',
    '↦': r'$\mapsto$',
    # Logic
    '∧': r'$\land$', '∨': r'$\lor$', '¬': r'$\neg$',
    # Misc
    '⊥': r'$\perp$', '∥': r'$\parallel$', '⊤': r'$\top$',
    '⊢': r'$\vdash$', '⊨': r'$\models$',
    '†': r'$\dagger$', '‡': r'$\ddagger$', 'ℓ': r'$\ell$',
    'ℕ': r'$\mathbb{N}$', 'ℤ': r'$\mathbb{Z}$', 'ℚ': r'$\mathbb{Q}$',
    'ℝ': r'$\mathbb{R}$', 'ℂ': r'$\mathbb{C}$',
}

# Subscript/superscript mappings
SUBSCRIPT_MAP = {
    '₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4',
    '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9',
    'ₐ': 'a', 'ₑ': 'e', 'ₕ': 'h', 'ᵢ': 'i', 'ⱼ': 'j',
    'ₖ': 'k', 'ₗ': 'l', 'ₘ': 'm', 'ₙ': 'n', 'ₒ': 'o',
    'ₚ': 'p', 'ᵣ': 'r', 'ₛ': 's', 'ₜ': 't', 'ᵤ': 'u',
    'ᵥ': 'v', 'ₓ': 'x',
}

SUPERSCRIPT_MAP = {
    '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
    '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9',
    'ⁿ': 'n', 'ⁱ': 'i',
}

# Emoji pattern (comprehensive Unicode ranges)
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"  # dingbats
    "\U000024C2-\U0001F251"  # enclosed characters
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols extended
    "\U00002600-\U000026FF"  # misc symbols
    "\U00002700-\U000027BF"  # dingbats
    "\U0001F004-\U0001F0CF"  # playing cards & mahjong
    "]+",
    flags=re.UNICODE
)


def remove_emojis(text: str) -> str:
    """Remove all emoji characters from text."""
    return EMOJI_PATTERN.sub('', text)


def convert_html_sub_sup(text: str) -> str:
    """Convert HTML <sub> and <sup> tags to LaTeX format."""
    text = re.sub(r'<sub>([^<]+)</sub>', r'$_{\1}$', text, flags=re.IGNORECASE)
    text = re.sub(r'<sup>([^<]+)</sup>', r'$^{\1}$', text, flags=re.IGNORECASE)
    return text


def convert_subscripts_superscripts(text: str) -> str:
    """Convert Unicode subscripts/superscripts to LaTeX format."""
    sub_chars = ''.join(SUBSCRIPT_MAP.keys())
    sup_chars = ''.join(SUPERSCRIPT_MAP.keys())

    def replace_subscript_sequence(match):
        base = match.group(1) if match.group(1) else ''
        subs = match.group(2)
        converted = ''.join(SUBSCRIPT_MAP.get(c, c) for c in subs)
        if base:
            return f'${base}_{{{converted}}}$'
        return f'$_{{{converted}}}$'

    def replace_superscript_sequence(match):
        base = match.group(1) if match.group(1) else ''
        sups = match.group(2)
        converted = ''.join(SUPERSCRIPT_MAP.get(c, c) for c in sups)
        if base:
            return f'${base}^{{{converted}}}$'
        return f'$^{{{converted}}}$'

    if sub_chars:
        text = re.sub(f'([A-Za-z0-9]?)([{re.escape(sub_chars)}]+)', replace_subscript_sequence, text)

    if sup_chars:
        text = re.sub(f'([A-Za-z0-9]?)([{re.escape(sup_chars)}]+)', replace_superscript_sequence, text)

    return text


def convert_math_symbols(text: str) -> str:
    """Convert Unicode math symbols to LaTeX equivalents."""
    for symbol, latex in MATH_REPLACEMENTS.items():
        text = text.replace(symbol, latex)
    return text


def fix_code_block_arrows(text: str) -> str:
    """
    Convert code blocks containing simple type mappings with arrows into inline code.

    Transforms:
        ```swift
        __CLPK_integer → Int32
        ```
    Into:
        `__CLPK_integer` $\\rightarrow$ `Int32`
    """
    # Single mapping in code block
    pattern = re.compile(
        r'```\w*\n'
        r'([^\n`]+?)\s*'
        r'(?:\$\\rightarrow\$|→)'
        r'\s*([^\n`]+?)\n'
        r'```',
        re.MULTILINE
    )

    def replace_mapping(match):
        left = match.group(1).strip()
        right = match.group(2).strip()
        return f'`{left}` $\\rightarrow$ `{right}`'

    text = pattern.sub(replace_mapping, text)

    # Multiple mappings in a single code block
    multi_pattern = re.compile(
        r'```\w*\n'
        r'((?:[^\n`]+?\s*(?:\$\\rightarrow\$|→)\s*[^\n`]+?\n)+)'
        r'```',
        re.MULTILINE
    )

    def replace_multi_mapping(match):
        lines = match.group(1).strip().split('\n')
        result_lines = []
        for line in lines:
            arrow_match = re.match(r'(.+?)\s*(?:\$\\rightarrow\$|→)\s*(.+)', line)
            if arrow_match:
                left = arrow_match.group(1).strip()
                right = arrow_match.group(2).strip()
                result_lines.append(f'`{left}` $\\rightarrow$ `{right}`')
            else:
                result_lines.append(line)
        return '\n'.join(result_lines)

    text = multi_pattern.sub(replace_multi_mapping, text)
    return text


def clean_text(text: str) -> str:
    """Apply all text transformations."""
    text = remove_emojis(text)
    text = convert_html_sub_sup(text)
    text = convert_subscripts_superscripts(text)
    text = convert_math_symbols(text)
    text = fix_code_block_arrows(text)

    # Remove horizontal rules (--- on its own line)
    lines = text.split('\n')
    lines = [line for line in lines if line.strip() != '---']
    text = '\n'.join(lines)

    return text


def normalize_whitespace(text: str) -> str:
    """Clean up whitespace: strip trailing spaces, limit consecutive blank lines."""
    lines = text.split('\n')
    lines = [line.rstrip() for line in lines]
    text = '\n'.join(lines)
    while '\n\n\n' in text:
        text = text.replace('\n\n\n', '\n\n')
    return text
