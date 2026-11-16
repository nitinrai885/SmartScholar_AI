"""Plain Python tools. Every function here is deterministic (no LLM involved)."""


def format_inr(amount):
    """Format a number the Indian way: 250000 -> ₹2,50,000."""
    number = int(round(amount))
    digits = str(abs(number))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return ("-" if number < 0 else "") + "₹" + digits
