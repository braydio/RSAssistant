# Task Packet Summaries

This directory contains one durable implementation/refresh closeout summary per canonical Packet ID.

Filename:

```text
<PACKET-ID>-SUMMARY.md
```

The required summary fields and user-facing handoff format are defined in the repository root `AGENTS.md`.

Rules:

- one summary per Packet ID;
- update the existing summary as the packet advances;
- include the packet's exact `Authoring chat:` URL when one is recorded;
- record failed validation, drift, blockers, and follow-up honestly;
- end with `## Next Handoff` so the next session can resume without reconstructing terminal history.
