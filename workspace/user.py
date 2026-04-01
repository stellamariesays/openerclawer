"""
user.py — About your human.

Who is the person this agent works with?
"""


def context() -> str:
    return """
## Your Human

- **Name:** [Name]
- **Timezone:** [e.g. GMT+8]
- **Pronouns:** [optional]
- **How to address them:** [e.g. "Hal", "Boss", first name]

Add anything your agent should always remember about this person.
"""
