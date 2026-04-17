"""
Shared configuration for DBLP analysis pipeline.
Paths, keywords, venue lists, and country-mapping logic.

Machine-specific paths live in config.py (not committed).
Copy config.example.py → config.py and edit for your machine.
"""

from __future__ import annotations

import os
import re
try:
    from config import DATA_DIR, OPENALEX_DIR, OPENALEX_MAILTO
except ImportError:
    from config import DATA_DIR, OPENALEX_DIR
    OPENALEX_MAILTO = 'you@example.com'

# Env var overrides config.py, so you can keep a shared config.py and still
# set your own email on the command line (e.g. in a SLURM job).
OPENALEX_MAILTO = os.environ.get('OPENALEX_MAILTO', OPENALEX_MAILTO)

# ── Derived paths ────────────────────────────────────────────────────────────
RAW_DIR        = DATA_DIR / 'raw'          # downloaded dblp files
PARSED_DIR     = DATA_DIR / 'parsed'       # intermediate CSVs
OUTPUT_DIR     = DATA_DIR / 'output'       # final counts / figures

DBLP_XML_GZ    = RAW_DIR / 'dblp.xml.gz'
DBLP_DTD       = RAW_DIR / 'dblp.dtd'

# ── Year range ───────────────────────────────────────────────────────────────
YEAR_MIN = 2015
YEAR_MAX = 2025

# ── AI keywords (from utils.py, English only – DBLP titles are English) ─────
AI_KEYWORDS = [kw.lower() for kw in [
    # Core AI
    "artificial intelligence",
    "deep learning",
    "neural network",
    "transformer",
    "diffusion model",
    "reinforcement learning",
    "self-supervised learning",
    "representation learning",
    "multi-agent",

    # LLMs
    "large language model",
    "foundation model",
    "language model",
    "pretrained",
    "pre-trained",

    # Specific model names
    "ChatGPT",
    "GPT",
    "Gemini",
    "Claude",
    "Llama",
    "DeepSeek",
    "Qwen",
    "Grok",

    # Safety / alignment
    "alignment",
    "AI safety",
    "adversarial attack",
    "adversarial examples",
    "explainable AI",
    "hallucination",
    "jailbreak",

    # Compute
    "TPU",

    # Multimodal
    "multimodal model",
    "vision-language model",
    "text-to-image",
    "text-to-video",
    "image generation",
    "video generation",

    # Applied AI
    "AI governance",
    "AI ethics",
    "AI adoption",
    "computational social science",
    "automation",

    # Additional for DBLP (common in CS conference titles)
    "graph neural network",
    "convolutional neural network",
    "recurrent neural network",
    "generative adversarial network",
    "variational autoencoder",
    "attention mechanism",
    "knowledge graph",
    "prompt tuning",
    "in-context learning",
    "chain-of-thought",
    "retrieval-augmented",
    "RLHF",
    "instruction tuning",
    "fine-tuning",
    "zero-shot",
    "few-shot",
]]

# NOTE: "AI", "LLM", "VLM" are short – match as whole words to reduce false positives
AI_KEYWORDS_WHOLE_WORD = [kw.lower() for kw in [
    "AI",
    "LLM",
    "VLM",
    "AIGC",
    "GAN",
    "NLP",
    "NLU",
    "NLG",
    "XAI",
]]

# Pre-compile regex for whole-word keywords
_whole_word_patterns = [re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
                        for kw in AI_KEYWORDS_WHOLE_WORD]


def is_ai_title(title: str) -> bool:
    """Check whether a paper title matches any AI keyword."""
    if not title:
        return False
    title_lower = title.lower()
    # substring match for longer keywords
    for kw in AI_KEYWORDS:
        if kw in title_lower:
            return True
    # whole-word match for short acronyms
    for pat in _whole_word_patterns:
        if pat.search(title):
            return True
    return False


# ── Key AI venues (conferences + journals) ──────────────────────────────────
# These are matched against DBLP's <booktitle> or <journal> fields.
# A paper from these venues is flagged as venue_is_ai=True regardless of title.
AI_VENUES = {v.lower() for v in [
    # Top ML / AI conferences
    "NeurIPS",
    "NIPS",
    "ICML",
    "ICLR",
    "AAAI",
    "IJCAI",
    "UAI",
    "AISTATS",
    "COLT",
    "ALT",

    # NLP
    "ACL",
    "EMNLP",
    "NAACL",
    "EACL",
    "COLING",
    "CoNLL",

    # Computer Vision
    "CVPR",
    "ICCV",
    "ECCV",
    "WACV",
    "BMVC",

    # Data Mining / Knowledge Discovery
    "KDD",
    "ICDM",
    "SDM",
    "CIKM",
    "WSDM",
    "WWW",

    # Robotics / multiagent
    "ICRA",
    "IROS",
    "RSS",
    "CoRL",
    "AAMAS",

    # Speech
    "INTERSPEECH",
    "ICASSP",

    # Information Retrieval
    "SIGIR",
    "ECIR",

    # General AI / misc
    "ECAI",
    "ACML",
    "PAKDD",
    "PRICAI",

    # Top AI journals
    "J. Mach. Learn. Res.",
    "JMLR",
    "Mach. Learn.",
    "Artif. Intell.",
    "J. Artif. Intell. Res.",
    "JAIR",
    "Neural Comput.",
    "IEEE Trans. Pattern Anal. Mach. Intell.",
    "TPAMI",
    "IEEE Trans. Neural Networks Learn. Syst.",
    "TNNLS",
    "Neural Networks",
    "Pattern Recognit.",
    "Int. J. Comput. Vis.",
    "IJCV",
]}


def is_ai_venue(venue: str) -> bool:
    """Check whether a venue name matches a known AI venue."""
    if not venue:
        return False
    venue_lower = venue.lower()
    for v in AI_VENUES:
        if v in venue_lower:
            return True
    return False


# ── Country keywords for affiliation matching ────────────────────────────────
# Used to infer country from DBLP <note type="affiliation"> text
CHINA_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    r'\bchina\b',
    r'\bP\.?\s*R\.?\s*China\b',
    r'\bbeijing\b',
    r'\bshanghai\b',
    r'\bshenzhen\b',
    r'\bhangzhou\b',
    r'\bnanjing\b',
    r'\bwuhan\b',
    r'\bguangzhou\b',
    r'\btsinghua\b',
    r'\bpeking\b',
    r'\bfudan\b',
    r'\bzhejiang\b',
    r'\bChinese Academy of Sciences\b',
    r'\bCAS\b',
    r'\bHong Kong\b',
    r'\bTaiwan\b',
    r'\bTaipei\b',
]]

US_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    r'\bUSA\b',
    r'\bUnited States\b',
    r'\bU\.?\s*S\.?\s*A\.?\b',
    r'\bCalifornia\b',
    r'\bMassachusetts\b',
    r'\bNew York\b',
    r'\bStanford\b',
    r'\bMIT\b',
    r'\bCarnegie Mellon\b',
    r'\bBerkeley\b',
    r'\bHarvard\b',
    r'\bGoogle\b',
    r'\bMicrosoft\b',
    r'\bMeta\b',
    r'\bOpenAI\b',
    r'\bIllinois\b',
    r'\bWashington\b',
    r'\bTexas\b',
    r'\bGeorgia\b',
    r'\bPennsylvania\b',
]]


def infer_country(affiliation: str) -> str | None:
    """Return 'CN' or 'US' from affiliation text, or None if unclear."""
    if not affiliation:
        return None
    for pat in CHINA_PATTERNS:
        if pat.search(affiliation):
            return 'CN'
    for pat in US_PATTERNS:
        if pat.search(affiliation):
            return 'US'
    return None
