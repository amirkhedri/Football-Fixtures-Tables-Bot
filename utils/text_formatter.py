# utils/text_formatter.py
import arabic_reshaper
from bidi.algorithm import get_display

def format_persian(text: str) -> str:
    """
    Reshapes and applies bidirectional algorithm for Persian/Arabic text 
    so it renders connected and right-to-left in Pillow.
    """
    if not text:
        return ""
    reshaped_text = arabic_reshaper.reshape(str(text))
    return get_display(reshaped_text)