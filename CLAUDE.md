At the start of every session, read ONLY these three files: CLAUDE.md (repo root), .agents/rules/context.md, and .agents/rules/decisions.md. Do not read, list, or explore any other files or directories at session start unless the user's message requires it for that specific task.

After completing any meaningful step (running the app, installing a dependency, changing a config, fixing a bug), immediately update context.md's relevant section before doing anything else. Never let context.md fall behind actual work done.

Also maintain decisions.md separately from context.md:
- context.md = task state (what's done, in progress, broken, current branch) — changes constantly
- decisions.md = durable architectural/technical decisions and why they were made — rarely changes, append-only

Whenever a real decision is made (choosing a library, rejecting an approach, picking a data model, changing a convention), append it to decisions.md immediately, in this format:
- **Decision:** <what was decided>
- **Why:** <reasoning>
- **Date/context:** <when/session it came from>

Also treat these as "meaningful steps" requiring an update, even if no files changed:
- Answering a research/investigation question (e.g. "can library X be integrated", "how does Y currently work")
- Reaching a conclusion or recommendation, even a tentative one

If the finding is a durable technical conclusion or recommendation (e.g. "yt-dlp is viable for sourcing comments because Z"), append it to decisions.md.
If the finding is still open/unresolved or needs follow-up, log it in context.md under "In Progress" instead.

Don't log routine task progress in decisions.md — that belongs in context.md. Don't log architectural reasoning in context.md — that belongs in decisions.md.