# Labelling guide: why does this fix fail?

Thank you for helping. This takes about 3 hours: 64 cases, about 3 minutes each. You don't need to run anything.

## The setting

An AI coding agent was given a bug report (an issue from a real open-source Python project) and asked to fix it.
It edited the code and ran the project's existing tests until they passed, then stopped. So **every fix here passed
the tests the agent could see.**

Each fix was then checked with hidden tests written by the project's own developers when they fixed the issue for
real. **Every fix in this packet failed those hidden tests.** Your job is to say *why*, in one category.

## What each case file shows

`cases/case-NN.md` has, in order:

1. **The issue**: the bug report the agent was given.
2. **The agent's fix**: a diff (lines starting `-` were removed, `+` were added).
3. **The official fix**: what the project's developers actually did.
4. **The official tests**: the tests the developers added or changed for this issue. These are the hidden tests.
5. **Which hidden tests failed**, and an excerpt of their output.

A good order: read the issue, then the failed test and its output, then compare the two fixes.

## The categories

Pick the **one** that best explains why the hidden tests fail.

**A. Unstated detail.** The agent's fix solves the problem the issue describes, but the hidden test checks a detail
the issue doesn't ask for, so the agent could not have known it. For example: the exact wording of an error message,
the name of a new argument or method, the exact return type or format, or a specific exception class, when the issue
leaves these open.
*Test: would a careful developer, reading only the issue, reasonably have written the agent's version?*

**B. Incomplete.** The fix is in the right place and handles the reported example, but misses part of what the issue
asks for or clearly implies: another input, another code path, a sibling function or class with the same problem
(e.g. fixes `__add__` but not `__radd__`, or one factory function but not its twin).

**C. Wrong fix.** The fix doesn't address the real cause: it changes the wrong place, patches over the symptom (e.g.
catches and hides an error rather than fixing why it happens), special-cases the example from the issue, or breaks
behaviour that was working (a previously passing test now fails).

**D. Evaluation problem.** The fix looks correct and complete, and the failure comes from something else: a test that
fails for reasons unrelated to the fix, an environment or import problem the fix didn't cause, or a test that
couldn't pass for any reasonable fix.

**E. Can't tell.** Use sparingly: only when you've read the case and genuinely can't decide.

If two categories fit, use this order: **D before A before B before C**. In other words, first ask "is the failure
the fix's fault at all?", then "could the agent have known?", then "right idea but not finished?", then "wrong idea".

## The sheet

Fill in `sheet.csv` (Excel, Numbers or Google Sheets all open it):

- `category`: A, B, C, D or E
- `sure`: `yes` or `no`, meaning you're confident or it was a close call
- `note`: optional, a few words (e.g. "misses the reverse operator", "error message wording")

## Rules

- **Work alone.** Don't discuss cases with the other labeller until you've both sent your sheets. The point is to
  measure how often two people agree independently.
- **Don't look anything up** beyond the case file, e.g. the project's GitHub history.
- You don't see which AI model wrote each fix, and that's deliberate. Don't try to guess it.
- If a case is very long, focus on the failed tests and their output.

Send the filled-in `sheet.csv` back when you're done.
