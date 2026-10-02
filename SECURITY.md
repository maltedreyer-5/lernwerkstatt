# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub:
**Security → Report a vulnerability** on
<https://github.com/maltedreyer-5/lernwerkstatt/security>. Do not open a
public issue.

Include what you found, how to reproduce it, and what an attacker could
achieve. You will get an answer within two weeks. Fixes are released as
soon as they are ready, and the advisory credits you unless you prefer
otherwise.

## Supported versions

Security fixes are made for the latest release.

## Scope

LernWerkstatt is designed for a trusted group of users behind access
control, not for the open internet; the
[security model](docs/operations.md#security-model) describes the
assumptions. Within that model, these are in scope, among others:

- code written by the model escaping the simulator sandbox at generation
  time or in a delivered unit;
- script execution in a delivered unit from generated content;
- access to another user's job without its pickup code;
- reading or writing files outside the work directory;
- a delivered unit contacting the network although it was built with
  embedded libraries.

Out of scope: the absence of user accounts, and the use of LLM quota by
anyone who can reach the interface. Both are consequences of the security
model and are documented.
