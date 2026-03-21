important_patterns = [
    "me llamo",
    "mi nombre es",
    "trabajo en",
    "mi empresa",
    "mi email",
    "mi edad"
]


def is_important(text):

    text = text.lower()

    for pattern in important_patterns:

        if pattern in text:
            return True

    return False