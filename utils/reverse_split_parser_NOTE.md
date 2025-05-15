# Reverse Split Parser Note

This file explains `tutils/reverse_split_parser.py` and its purpose.

- It provides a single function: ``get_reverse_split_handler_from_url`(url)``.
- This function automatically fetches the page content at that URL.
- It looks for named split handlers like **Roundup** or **Cache & Loo**
- It can be extended to support more names or keywords.