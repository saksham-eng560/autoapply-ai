"""Generic form-filling engine used by every platform submitter.

1. ``extract_fields`` inspects the live DOM and returns every fillable control with its best
   human-readable label, type, options and a stable ``data-aa-id`` handle.
2. ``classify_field`` maps a control to a profile value / resume upload / cover letter / question.
3. ``fill_field`` writes a value with the right interaction for the control type (text, select,
   radio, checkbox, file, React comboboxes), using human-like typing when enabled.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.automation.human import human_click, human_type, short_pause
from app.services.question_answerer import choose_option
from app.services.text_utils import normalize_text

logger = logging.getLogger(__name__)

EXTRACT_JS = r"""
(rootSelector) => {
  const root = (rootSelector && document.querySelector(rootSelector)) || document;
  const clean = (t) => (t || '').replace(/\s+/g, ' ').replace(/\*/g, '').trim();
  const visible = (el) => {
    if (el.type === 'file') return true;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return (r.width > 0 && r.height > 0) || el.getAttribute('role') === 'combobox';
  };
  const labelFor = (el) => {
    if (el.id) {
      const l = root.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l && clean(l.innerText)) return clean(l.innerText);
    }
    const by = el.getAttribute('aria-labelledby');
    if (by) {
      const t = by.split(/\s+/).map(id => document.getElementById(id)).filter(Boolean).map(n => n.innerText).join(' ');
      if (clean(t)) return clean(t);
    }
    if (el.getAttribute('aria-label')) return clean(el.getAttribute('aria-label'));
    const wrap = el.closest('label');
    if (wrap && clean(wrap.innerText)) return clean(wrap.innerText);
    let node = el.parentElement;
    for (let i = 0; i < 5 && node; i++, node = node.parentElement) {
      const cand = node.querySelector('label, legend, .label, [class*="label"], [class*="question"], [data-automation-id*="formLabel"]');
      if (cand && !cand.contains(el) && clean(cand.innerText)) return clean(cand.innerText);
    }
    return clean(el.getAttribute('placeholder') || el.name || el.id || '');
  };
  const groupLabel = (el) => {
    const fs = el.closest('fieldset');
    if (fs) { const lg = fs.querySelector('legend'); if (lg && clean(lg.innerText)) return clean(lg.innerText); }
    let node = el.parentElement;
    for (let i = 0; i < 6 && node; i++, node = node.parentElement) {
      const cand = node.querySelector('legend, .label, [class*="label"]:not(label), [class*="question"], [data-automation-id*="formLabel"]');
      if (cand && !cand.contains(el) && clean(cand.innerText)) return clean(cand.innerText);
    }
    return clean(el.name || '');
  };
  const fields = [];
  const seenGroups = new Set();
  let counter = 0;
  const els = root.querySelectorAll('input, select, textarea, [role="combobox"], [contenteditable="true"]');
  for (const el of els) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || (tag === 'select' ? 'select' : tag === 'textarea' ? 'textarea' : el.getAttribute('role') === 'combobox' ? 'combobox' : 'text')).toLowerCase();
    if (['hidden', 'submit', 'button', 'image', 'reset', 'search'].includes(type)) continue;
    if (tag === 'input' && el.getAttribute('role') === 'combobox' && type !== 'text') continue;
    if (!visible(el) || el.disabled || el.readOnly && type !== 'file') continue;
    if (el.closest('[aria-hidden="true"]') && type !== 'file') continue;
    const required = el.required || el.getAttribute('aria-required') === 'true' || /\*/.test((el.closest('div,li,fieldset') || {}).innerText || '');
    if (type === 'radio' || type === 'checkbox') {
      const key = el.name || el.id;
      const group = el.name ? Array.from(root.querySelectorAll(`input[type="${type}"][name="${CSS.escape(el.name)}"]`)) : [el];
      if (group.length > 1 || type === 'radio') {
        if (seenGroups.has(key)) continue;
        seenGroups.add(key);
        const handle = `aa-${counter++}`;
        const options = group.map(o => { o.setAttribute('data-aa-group', handle); return labelFor(o) || o.value; });
        fields.push({ handle, tag, type, name: el.name, id: el.id, label: groupLabel(el), required, options, value: '', autocomplete: '' });
        continue;
      }
    }
    const handle = `aa-${counter++}`;
    el.setAttribute('data-aa-id', handle);
    let options = [];
    if (tag === 'select') options = Array.from(el.options).filter(o => o.value !== '' || o.text.trim()).map(o => o.text.trim()).filter(t => t && !/^(select|choose|--|please select)/i.test(t));
    fields.push({
      handle, tag, type, name: el.name || '', id: el.id || '', label: labelFor(el), required, options,
      value: type === 'file' ? '' : (el.value || ''), autocomplete: el.getAttribute('autocomplete') || '',
      accept: el.getAttribute('accept') || '', multiple: !!el.multiple,
    });
  }
  return fields;
}
"""


@dataclass
class FormField:
    handle: str
    tag: str
    type: str
    label: str
    name: str = ""
    id: str = ""
    required: bool = False
    options: list[str] = field(default_factory=list)
    value: str = ""
    autocomplete: str = ""
    accept: str = ""
    multiple: bool = False

    @property
    def selector(self) -> str:
        if self.type in ("radio", "checkbox") and self.options:
            return f'[data-aa-group="{self.handle}"]'
        return f'[data-aa-id="{self.handle}"]'

    @property
    def descriptor(self) -> str:
        return normalize_text(f"{self.label} {self.name} {self.id} {self.autocomplete}")

    def as_question(self) -> dict[str, Any]:
        field_type = {"select": "select", "radio": "radio", "checkbox": "checkbox", "number": "number",
                      "combobox": "select"}.get(self.type, "text")
        return {"question": self.label or self.name, "field_type": field_type, "options": self.options,
                "required": self.required, "field_id": self.handle}


def extract_fields(page: Any, root_selector: str | None = None) -> list[FormField]:
    raw = page.evaluate(EXTRACT_JS, root_selector)
    fields = []
    for item in raw:
        fields.append(FormField(**{k: item.get(k) for k in FormField.__dataclass_fields__ if k in item}))
    return fields


# --------------------------------------------------------------------------- classification
PROFILE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("resume", re.compile(r"resume|\bcv\b|curriculum")),
    ("cover_letter", re.compile(r"cover.?letter|motivation letter")),
    ("first_name", re.compile(r"first.?name|given.?name|\bfname\b|given-name|legalnamesection_firstname|preferred first")),
    ("last_name", re.compile(r"last.?name|family.?name|surname|\blname\b|family-name|legalnamesection_lastname")),
    ("full_name", re.compile(r"^(your )?(full |legal )?name\b|^name$|full.?name|\bname$")),
    ("email", re.compile(r"e-?mail")),
    ("phone", re.compile(r"phone|mobile|\btel\b|cell")),
    ("linkedin", re.compile(r"linked.?in")),
    ("github", re.compile(r"github")),
    ("portfolio", re.compile(r"portfolio|personal (web)?site|website|\burl\b|urls\[other\]")),
    ("current_company", re.compile(r"current (company|employer)|^org$|\borg\b|company name|most recent (company|employer)")),
    ("current_title", re.compile(r"current (job )?title|current role|job title")),
    ("location", re.compile(r"^location|current location|candidate-location|city,? state|where are you (located|based)|^city$")),
]


def classify_field(f: FormField) -> str | None:
    desc = f.descriptor
    if f.type == "file":
        if re.search(r"cover", desc):
            return "cover_letter"
        return "resume"  # any other file upload on an application form is the resume/CV
    for key, pattern in PROFILE_PATTERNS:
        if key in ("resume",) and f.type != "file":
            continue
        if pattern.search(desc):
            if key == "cover_letter" and f.type not in ("textarea", "file", "text", "contenteditable"):
                continue
            if key == "full_name" and re.search(r"company|school|university|reference|emergency|manager|recruiter", desc):
                continue
            if key in ("email", "phone") and re.search(r"reference|emergency", desc):
                continue
            return key
    if f.autocomplete in ("given-name", "family-name", "email", "tel", "name"):
        return {"given-name": "first_name", "family-name": "last_name", "email": "email", "tel": "phone", "name": "full_name"}[f.autocomplete]
    return None


# --------------------------------------------------------------------------- filling
def fill_field(page: Any, f: FormField, value: Any) -> bool:
    """Fill one control. Returns True when the value was applied."""
    if value is None or value == "":
        return False
    try:
        if f.type == "file":
            page.locator(f.selector).first.set_input_files(value)
            return True
        if f.type == "select":
            loc = page.locator(f.selector).first
            choice = choose_option(str(value), f.options) if f.options else str(value)
            try:
                loc.select_option(label=choice)
            except Exception:  # noqa: BLE001
                loc.select_option(value=choice)
            return True
        if f.type == "radio":
            choice = choose_option(str(value), f.options)
            if choice not in f.options:
                return False
            idx = f.options.index(choice)
            option = page.locator(f.selector).nth(idx)
            try:
                option.check(force=True)
            except Exception:  # noqa: BLE001
                human_click(page, option)
            return True
        if f.type == "checkbox":
            if f.options and len(f.options) > 1:
                wanted = [v.strip() for v in str(value).split(",")] if isinstance(value, str) else list(value)
                done = False
                for w in wanted:
                    choice = choose_option(w, f.options)
                    if choice in f.options:
                        page.locator(f.selector).nth(f.options.index(choice)).check(force=True)
                        done = True
                return done
            truthy = normalize_text(str(value)) in ("yes", "true", "1", "checked", "agree", "i agree", "y")
            loc = page.locator(f.selector).first
            if truthy:
                loc.check(force=True)
            else:
                loc.uncheck(force=True)
            return True
        if f.type == "combobox" or (f.tag == "input" and f.type == "text" and _is_combobox(page, f)):
            return _fill_combobox(page, f, str(value))
        loc = page.locator(f.selector).first
        if f.type == "contenteditable":
            loc.click()
            page.keyboard.type(str(value))
            return True
        human_type(page, loc, str(value))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to fill %s (%s): %s", f.label, f.selector, exc)
        return False


def _is_combobox(page: Any, f: FormField) -> bool:
    try:
        return page.locator(f.selector).first.get_attribute("role") == "combobox"
    except Exception:  # noqa: BLE001
        return False


def _fill_combobox(page: Any, f: FormField, value: str) -> bool:
    """React-select / ARIA comboboxes (Greenhouse, Workday): type, then pick the best matching option."""
    loc = page.locator(f.selector).first
    loc.click()
    short_pause()
    try:
        loc.fill("")
        loc.type(value[:40], delay=40)
    except Exception:  # noqa: BLE001
        page.keyboard.type(value[:40], delay=40)
    page.wait_for_timeout(700)
    options = page.locator('[role="option"], [class*="select__option"], [data-automation-id="promptOption"]')
    count = options.count()
    if count:
        texts = [options.nth(i).inner_text().strip() for i in range(min(count, 50))]
        choice = choose_option(value, texts)
        idx = texts.index(choice) if choice in texts else 0
        options.nth(idx).click()
        return True
    page.keyboard.press("Enter")
    return True


def visible_errors(page: Any) -> list[str]:
    """Collect validation error messages currently shown on the page."""
    try:
        return page.evaluate(
            r"""() => Array.from(document.querySelectorAll('[aria-invalid="true"], .error, .field-error, [class*="error-message"], [role="alert"], [data-automation-id="errorMessage"]'))
                  .map(e => (e.innerText || e.getAttribute('aria-label') || e.name || '').trim())
                  .filter(t => t && t.length < 300).slice(0, 10)"""
        )
    except Exception:  # noqa: BLE001
        return []


CONFIRMATION_PATTERN = re.compile(
    r"thank(s| you) for (applying|your application|your interest)|application (has been |was )?(submitted|received|sent|complete)"
    r"|we('|’)ve received your application|your application was sent|successfully (submitted|applied)|application submitted",
    re.IGNORECASE,
)


def looks_submitted(page: Any) -> tuple[bool, str | None]:
    try:
        url = page.url.lower()
        text = page.inner_text("body")[:20000]
    except Exception:  # noqa: BLE001
        return False, None
    m = CONFIRMATION_PATTERN.search(text)
    if m or re.search(r"confirm|thank|success|submitted", url):
        num = re.search(r"(?:confirmation|reference|application)\s*(?:number|#|id)[:\s#]*([A-Z0-9-]{4,})", text, re.I)
        return True, num.group(1) if num else None
    return False, None
