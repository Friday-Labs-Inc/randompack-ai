"""Which phase outputs the studio's client receives, and their human titles.

Contributed to the kernel's deliverable materializer through the
``friday_customer_title_map`` hook (file_name prefix -> customer-facing title;
newest version of each prefix wins).
"""

CUSTOMER_TITLE_MAP: list[tuple[str, str]] = [
	("brand-guidelines", "Brand Guidelines"),
	("production-package", "Brand System — Production Package"),
	("gate2-final-review", "Final Review (Gate 2)"),
	("gate1-client-presentation", "Direction Presentation (Gate 1)"),
	("naming-candidates", "Naming Candidates"),
	("strategy", "Brand Strategy"),
]
