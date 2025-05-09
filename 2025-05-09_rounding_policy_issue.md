# Rounding Policy Error Report - 2025-05-09

** Date: 2025-05-09
** Title: Undefined Function - Rounding Policy Anomaly

Functional error was encountered while triggering the rounding policy alert. Specifically, the function appeared not to be defined in the calling context.

The logic resides in:
 - `utils/on_message_utils.py` as method `in_round_up_policy` included in the `OnMessagePolicyResolver` class
  - Primary file `RSAssistant.py` calls the `triggers` routine but does not import or define the function required explicitly

The error can be fixed by:
** ensuring that an ymodicule like `in_round_up_policy()` is never called outside of the utils file
*** importing the class from utils when its methods need to be used directly


[View Update on: GitHub](https://github.com/braydio/RSAssistant)
