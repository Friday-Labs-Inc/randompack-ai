"""Which phase outputs the studio's client receives, and their human titles.

Contributed to the kernel's deliverable materializer through the
``friday_customer_title_map`` hook (file_name prefix -> customer-facing title;
newest version of each prefix wins).
"""

CUSTOMER_TITLE_MAP: list[tuple[str, str]] = [
	("brand-guidelines", "Brand Guidelines"),
	("production-package", "Brand System — Production Package"),
	# No gate numbers in a client-facing title: a studio may quote three gates
	# and name each one itself, so "(Gate 2)" is a claim about a shape the
	# proposal no longer guarantees.
	# One prefix for every client decision, because the pipeline no longer has a
	# fixed number of them. The two below it are the retired two-gate machine.
	("gate-presentation", "Client Review"),
	("gate2-final-review", "Final Review"),
	("gate1-client-presentation", "Direction Presentation"),
	("naming-candidates", "Naming Candidates"),
	("strategy", "Brand Strategy"),
]
