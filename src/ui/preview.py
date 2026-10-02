# -*- coding: utf-8 -*-
"""Preparing a generated unit for the preview in the wizard.

Kept free of Gradio so that it can be tested without the interface.
"""


def for_preview(html: str) -> str:
    """Prepares a generated unit for the preview iframe (srcdoc).

    Inside srcdoc, links such as `#lesson` resolve against the address of
    the surrounding page, so a click navigated the preview to the wizard
    itself instead of to the lesson. A base of about:srcdoc keeps them in
    the document. Only the preview is changed; the delivered file is not.
    """
    basis = '<base href="about:srcdoc">'
    if "<head>" in html:
        return html.replace("<head>", "<head>" + basis, 1)
    return basis + html
